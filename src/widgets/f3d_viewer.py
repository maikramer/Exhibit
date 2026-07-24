# f3d_viewer.py
#
# Copyright 2024-2025 Nokse <nokse@posteo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import ctypes
import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Gdk, GLib, Gio, GObject

import f3d

from ..camera_nav import (
    NAV_SETTING_DEFAULTS,
    axis_delta,
    clamp_dolly_factor,
    clamp_scroll_delta,
    clamp_sensitivity,
    depth_distance,
    dolly_to_cursor,
    gtk_to_display,
    is_sane_pivot,
    orbit_rig_around_pivot,
    pan_scale_for_distance,
    pivot_camera_to_point,
)
from ..camera_views import UP_DIRS, apply_view
from ..vector_math import p_dist, v_abs, v_add, v_sub, v_mul, v_dot_p
from .. import logger_lib
from .f3d_viewer_load import F3DLoadMixin


def _gl_get_proc_address(lib_name: str, symbol: str):
    """Return a ``get_proc_address`` callable for F3D ``create_external``."""
    lib = ctypes.CDLL(lib_name)
    fn = getattr(lib, symbol)
    fn.restype = ctypes.c_void_p
    fn.argtypes = [ctypes.c_char_p]

    def get_proc_address(name):
        if isinstance(name, str):
            name = name.encode("ascii")
        return fn(name)

    return get_proc_address

# Back-compat alias used across pan/tilt helpers.
up_dirs_vector = UP_DIRS


@Gtk.Template(resource_path="/io/github/nokse22/Exhibit/ui/f3d_viewer.ui")
class F3DViewer(F3DLoadMixin, Gtk.GLArea):
    __gtype_name__ = "F3DViewer"

    keys = {
        "grid": "render.grid.enable",
        "grid-absolute": "render.grid.absolute",
        # Bool UI → enum options (F3D master / post-3.5 API)
        "translucency-support": "render.effect.blending.mode",
        "tone-mapping": "render.effect.tone_mapping",
        "ambient-occlusion": "render.effect.ambient_occlusion",
        "anti-aliasing": "render.effect.antialiasing.mode",
        "hdri-ambient": "render.hdri.ambient",
        "hdri-skybox": "render.background.skybox",
        "light-intensity": "render.light.intensity",
        "orthographic": "scene.camera.orthographic",
        "blur-background": "render.background.blur.enable",
        "blur-coc": "render.background.blur.coc",
        "bg-color": "render.background.color",
        "show-edges": "render.show_edges",
        "edges-width": "render.line_width",
        "up": "scene.up_direction",
        # sprite-enabled is folded into model.point_sprites.type ("none" when off)
        "sprite-enabled": "model.point_sprites.type",
        "sprites-size": "model.point_sprites.size",
        "sprites-type": "model.point_sprites.type",
        "point-size": "render.point_size",
        "model-color": "model.color.rgb",
        "model-metallic": "model.material.metallic",
        "model-roughness": "model.material.roughness",
        "model-opacity": "model.color.opacity",
        "scivis-component": "model.scivis.component",
        "hdri-file": "render.hdri.file",
        "cells": "model.scivis.cells",
        "scivis-enabled": "model.scivis.enable",
        "armature-enable": "render.armature.enable",
        "checkerboard-enable": "model.checkerboard.enable",
        "normal-glyphs": "model.normal_glyphs.enable",
        "normal-glyphs-scale": "model.normal_glyphs.scale",
        "display-depth": "render.effect.display_depth",
        # The following settings don't have an UI
        "texture-matcap": "model.matcap.texture",
        "texture-base-color": "model.color.texture",
        "emissive-factor": "model.emissive.factor",
        "texture-emissive": "model.emissive.texture",  # rename to material-emissive
        "texture-material": "model.material.texture",  # rename to material-texture
        "normal-scale": "model.normal.scale",
        "texture-normal": "model.normal.texture",  # rename to normal-texture
        "volume": "model.volume.enable",  # rename to volume-enabled
        "inverse": "model.volume.inverse",  # rename to volume-inverse
        "final-shader": "render.effect.final_shader",
        "grid-unit": "render.grid.unit",
        "grid-subdivisions": "render.grid.subdivisions",
        "grid-color": "render.grid.color",
        "scalar": "model.scivis.array_name",
        "scalar-bar": "ui.scalar_bar",
        "animation-index": "scene.animation.indices",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger_lib.logger

        self.engine = None
        self.scene = None
        self.window = None
        self.camera = None

        # Cached UI values for enum options that replaced bools in recent F3D.
        self._sprite_enabled = False
        self._sprites_type = "sphere"

        f3d.Log.set_use_coloring(True)
        f3d.Log.set_verbose_level(f3d.Log.WARN)

        self.action_group = Gio.SimpleActionGroup()
        self.insert_action_group("f3dviewer", self.action_group)
        # Optional: window sets this to sync peer-tab cameras (compare mode).
        self.camera_changed_cb = None

        self.create_action(
            "toggle-orthographic",
            lambda *_: self.toggle_orthographic(),
        )
        self.create_action("front-view", self.front_view)
        self.create_action("right-view", self.right_view)
        self.create_action("back-view", self.back_view)
        self.create_action("left-view", self.left_view)
        self.create_action("top-view", self.top_view)
        self.create_action("isometric-view", self.isometric_view)

        self.create_action("move-forward", self.pan_action, 0, 0, 1)
        self.create_action("move-left", self.pan_action, -1, 0, 0)
        self.create_action("move-backward", self.pan_action, 0, 0, -1)
        self.create_action("move-right", self.pan_action, 1, 0, 0)

        self.create_action("tilt-left", self.tilt_action, "left")
        self.create_action("tilt-right", self.tilt_action, "right")
        self.create_action("tilt-up", self.tilt_action, "up")
        self.create_action("tilt-down", self.tilt_action, "down")

        # Idle: demand-driven paints. Playback enables continuous auto-render.
        self.set_auto_render(False)
        # self.connect("realize", self.on_realize)
        self.connect("render", self.on_render)
        self.connect("resize", self.on_resize)

        self.settings = {
            # "scene.up_direction": "+Y",
            # "model.scivis.cells": True,
            # "model.scivis.array_name": "",
            # "render.hdri.ambient": False,
            "render.grid.enable": True
        }

        self.prev_pan_offset = 0
        self.drag_prev_offset = (0, 0)
        self.drag_start_angle = 0
        self._pointer_xy = (0.0, 0.0)
        self._drag_start_xy = (0.0, 0.0)
        self._drag_mode = "orbit"
        self._drag_button = 0
        self._drag_moved = False
        # Pivot mode captured at drag-begin (Alt toggles prefs for that gesture).
        self._drag_orbit_around_cursor = False
        self._drag_zoom_to_cursor = True
        self._drag_use_cursor_depth = True
        # Pixels of movement before a press counts as a drag (not a click).
        self._click_drag_threshold = 4.0

        self.always_point_up = True
        # Navigation prefs (wired from WindowSettings / gschema).
        self.nav_invert_x = bool(NAV_SETTING_DEFAULTS["nav-invert-x"])
        self.nav_invert_y = bool(NAV_SETTING_DEFAULTS["nav-invert-y"])
        self.nav_zoom_to_cursor = bool(NAV_SETTING_DEFAULTS["nav-zoom-to-cursor"])
        self.nav_orbit_around_cursor = bool(
            NAV_SETTING_DEFAULTS["nav-orbit-around-cursor"]
        )
        self.nav_touchpad_orbit = bool(NAV_SETTING_DEFAULTS["nav-touchpad-orbit"])
        self.nav_mmb_click_pivot = bool(NAV_SETTING_DEFAULTS["nav-mmb-click-pivot"])
        self.nav_orbit_sensitivity = float(
            NAV_SETTING_DEFAULTS["nav-orbit-sensitivity"]
        )
        self.nav_zoom_sensitivity = float(NAV_SETTING_DEFAULTS["nav-zoom-sensitivity"])
        self.nav_pan_sensitivity = float(NAV_SETTING_DEFAULTS["nav-pan-sensitivity"])

        self.prev_scale = 1

        self.distance = 0
        self.width = 1
        self.height = 1

        self._orthographic = False

        self._animation_time = 0
        self._playing = False
        self._animation_tick_ms = 16
        self._animation_tick_dt = 0.016
        self._animation_source_id = 0
        self._loaded_filepath = None
        self._prepared_path = None
        self._hidden_part_indices: set[int] = set()
        self._suppress_render = False

        self.set_allowed_apis(Gdk.GLAPI.GL)
        # Lazy engine: create on first load so extra tabs paint their
        # loading cover before paying for a new F3D/EGL context.

    def initialize(self):
        if self.engine is not None:
            self.logger.debug("F3D viewer already initialized; reusing engine")
            return

        if not self.get_realized():
            raise RuntimeError("GLArea not realized yet")

        # F3D create_external needs the Gtk.GLArea context current.
        self.make_current()
        gl_error = self.get_error()
        if gl_error is not None:
            raise RuntimeError(f"GLArea context error: {gl_error}")

        backends_list = f3d.Engine.get_rendering_backend_list()
        self.logger.info(f"Available F3D backends: {backends_list}")

        errors: list[str] = []
        # F3D 3.5+: create_external(get_proc_address). create_external_egl()
        # often fails inside Flatpak ("Cannot find EGL library") even when
        # libEGL.so.1 is present — bind via eglGetProcAddress instead.
        factories: list[tuple[str, object]] = []
        if GLib.getenv("WAYLAND_DISPLAY"):
            try:
                gpa = _gl_get_proc_address("libEGL.so.1", "eglGetProcAddress")
                factories.append(
                    ("external+eglGetProcAddress", lambda g=gpa: f3d.Engine.create_external(g))
                )
            except OSError as exc:
                errors.append(f"eglGetProcAddress setup: {exc}")
            factories.append(("external_egl", f3d.Engine.create_external_egl))
        if GLib.getenv("DISPLAY"):
            for symbol in ("glXGetProcAddressARB", "glXGetProcAddress"):
                try:
                    gpa = _gl_get_proc_address("libGL.so.1", symbol)
                    factories.append(
                        (
                            f"external+{symbol}",
                            lambda g=gpa: f3d.Engine.create_external(g),
                        )
                    )
                    break
                except (OSError, AttributeError) as exc:
                    errors.append(f"{symbol} setup: {exc}")
            factories.append(("external_glx", f3d.Engine.create_external_glx))

        for label, factory in factories:
            try:
                self.logger.info(f"Initializing F3D with {label}")
                self.engine = factory()
                if self.engine is not None:
                    break
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                self.engine = None

        if not self.engine:
            detail = "; ".join(errors) if errors else "no backend succeeded"
            self.logger.critical(f"Failed to initialize F3D: {detail}")
            raise RuntimeError(f"Failed to initialize F3D: {detail}")

        self.scene = self.engine.scene
        self.window = self.engine.window
        self.camera = self.window.camera

        self.engine.autoload_plugins()
        self.engine.options.update(self.settings)

        self.logger.info("F3D viewer initialized successfully")

    @GObject.Property(type=float)
    def upper_time_range(self):
        if self.scene is None:
            return 0.0
        _lower, upper = self.scene.animation_time_range()
        if upper != upper or abs(upper) == float("inf"):  # NaN or ±inf
            return 0.0
        return upper

    @GObject.Property(type=float)
    def lower_time_range(self):
        if self.scene is None:
            return 0.0
        lower, _upper = self.scene.animation_time_range()
        if lower != lower or abs(lower) == float("inf"):
            return 0.0
        return lower

    @GObject.Property(type=float)
    def animation_time(self):
        return self._animation_time

    @animation_time.setter
    def animation_time(self, value):
        self._animation_time = value
        if self.scene is None:
            return
        self.scene.load_animation_time(self._animation_time)
        self.queue_render()

    @GObject.Property(type=bool, default=False)
    def playing(self):
        return self._playing

    @playing.setter
    def playing(self, value):
        was_playing = self._playing
        self._playing = value

        if self._playing:
            if self.animation_time >= self.upper_time_range:
                self.animation_time = self.lower_time_range
            self.set_auto_render(True)
            if not was_playing:
                self._animation_source_id = GLib.timeout_add(
                    self._animation_tick_ms, self._advance_animation)
        else:
            self._stop_animation_timer()
            self.set_auto_render(False)
            if self.engine is not None:
                self.queue_render()

    def _stop_animation_timer(self) -> None:
        source_id = self._animation_source_id
        self._animation_source_id = 0
        if source_id:
            try:
                GLib.source_remove(source_id)
            except Exception as exc:
                if self.logger:
                    self.logger.debug("stop_animation_timer: %s", exc)

    def _advance_animation(self):
        if not self._playing or self.scene is None:
            self._animation_source_id = 0
            return GLib.SOURCE_REMOVE
        self.animation_time = self.animation_time + self._animation_tick_dt
        if self.animation_time >= self.upper_time_range:
            # Clear id before setter so source_remove is not called mid-callback.
            self._animation_source_id = 0
            self.playing = False
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    @GObject.Property(type=bool, default=False)
    def orthographic(self):
        return self._orthographic

    @orthographic.setter
    def orthographic(self, value):
        self._orthographic = value
        self.update_options({"orthographic": self._orthographic})
        self.notify("orthographic")

    def toggle_orthographic(self, *args):
        self.orthographic = not self.orthographic

    def reset_to_bounds(self):
        if self.camera is None:
            return
        self.camera.reset_to_bounds()
        self.get_distance()
        self._finalize_camera_nav()

    def front_view(self, *args):
        apply_view(self.camera, "front", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()
        self._notify_camera_changed()

    def right_view(self, *args):
        apply_view(self.camera, "right", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()
        self._notify_camera_changed()

    def back_view(self, *args):
        apply_view(self.camera, "back", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()
        self._notify_camera_changed()

    def left_view(self, *args):
        apply_view(self.camera, "left", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()
        self._notify_camera_changed()

    def top_view(self, *args):
        apply_view(self.camera, "top", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()
        self._notify_camera_changed()

    def isometric_view(self, *args):
        apply_view(self.camera, "isometric", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()
        self._notify_camera_changed()

    def _map_setting_to_f3d(self, key, value):
        """Translate Exhibit settings to current F3D option names/values."""
        if key == "translucency-support":
            return "render.effect.blending.mode", ("ddp" if value else "none")
        if key == "anti-aliasing":
            return "render.effect.antialiasing.mode", ("fxaa" if value else "none")
        if key == "sprite-enabled":
            self._sprite_enabled = bool(value)
            sprite_type = self._sprites_type if self._sprite_enabled else "none"
            return "model.point_sprites.type", sprite_type
        if key == "sprites-type":
            self._sprites_type = value if value else "sphere"
            sprite_type = self._sprites_type if self._sprite_enabled else "none"
            return "model.point_sprites.type", sprite_type
        if key == "animation-index":
            # F3D: empty indices = no animation. Python bindings reject []
            # but accept "" which clears the vector.
            if value is None:
                return self.keys[key], ""
            if isinstance(value, (list, tuple)):
                return self.keys[key], value if value else ""
            return self.keys[key], [int(value)]
        return self.keys[key], value

    def update_options(self, options, *, queue_render=True):
        # Prefer bulk sprite state so type/enable order does not matter.
        if "sprite-enabled" in options:
            self._sprite_enabled = bool(options["sprite-enabled"])
        if "sprites-type" in options and options["sprites-type"]:
            self._sprites_type = options["sprites-type"]

        f3d_options = {}
        for key, value in options.items():
            if key not in self.keys:
                continue
            f3d_key, mapped = self._map_setting_to_f3d(key, value)
            self.settings[f3d_key] = mapped
            f3d_options[f3d_key] = mapped

        self.logger.debug(f"f3d options update: {f3d_options}")
        if self.engine and f3d_options:
            self.engine.options.update(f3d_options)
            if queue_render and not self._suppress_render:
                self.queue_render()

    def begin_options_batch(self):
        self._suppress_render = True

    def end_options_batch(self):
        self._suppress_render = False
        self.queue_render()

    def available_animations(self):
        if not self.scene:
            return 0
        return int(self.scene.available_animations())

    def get_animation_names(self):
        if not self.scene:
            return []
        return list(self.scene.get_animation_names())

    def get_animation_keyframes(self) -> list[float]:
        """Keyframe times for the current animation selection (F3D 3.5+)."""
        if not self.scene:
            return []
        getter = getattr(self.scene, "get_animation_keyframes", None)
        if not callable(getter):
            return []
        try:
            return [float(t) for t in getter()]
        except Exception as exc:
            if self.logger:
                self.logger.debug("get_animation_keyframes failed: %s", exc)
            return []



    def render_image(self):
        self.get_context().make_current()
        img = self.window.render_to_image()
        # print(img.to_terminal_text())
        return img
















    def done(self):
        if self.settings.get("render.hdri.ambient") and self.engine:
            self.engine.options.update({"render.hdri.ambient": True})
            self.queue_render()

        self.reset_to_bounds()
        return GLib.SOURCE_REMOVE

    def on_resize(self, gl_area, width, height):
        self.width = width
        self.height = height

    def on_render(self, area, ctx):
        if self.window is None or not hasattr(self, "width") or not hasattr(self, "height"):
            return False
        self.window.size = self.width, self.height
        self.window.render()
        return True

    def get_camera_to_focal_distance(self):
        up = up_dirs_vector[self.settings["scene.up_direction"]]
        pos = self.camera.position
        foc = self.camera.focal_point

        pos_proj = v_sub(v_dot_p(pos, v_abs(up)), pos)
        foc_proj = v_sub(v_dot_p(foc, v_abs(up)), foc)

        dist = p_dist(pos_proj, foc_proj)

        pos_height = v_dot_p(pos, v_abs(up))
        foc_height = v_dot_p(foc, v_abs(up))

        diff = v_sub(pos_height, foc_height)

        for number in diff:
            if number != 0:
                return dist, (1 if number > 0 else -1)
        return dist, 1

    def get_gimble_limit(self):
        return self.distance / 10

    def get_distance(self):
        self.distance = p_dist(self.camera.position, self.camera.focal_point)

    def pan(self, x, y, z):
        val = self.distance / 40
        self.camera.pan(x * val, y * val, z * val)
        self.queue_render()

    def pan_action(self, action, _, x, y, z):
        self.pan(x, y, z)

    def tilt_action(self, action, _, direction):
        self.tilt(direction)

    def tilt(self, direction):
        val = self.distance / 40

        focal_point = self.camera.focal_point

        match direction:
            case "left":
                self.camera.pan(-val, 0, 0)
                self.camera.focal_point = focal_point
            case "right":
                self.camera.pan(val, 0, 0)
                self.camera.focal_point = focal_point
            case "up":
                dist, direction = self.get_camera_to_focal_distance()
                if dist > self.get_gimble_limit() or (
                    dist < self.get_gimble_limit() and direction == -1
                ):
                    self.camera.pan(0, val, 0)
                    self.camera.focal_point = focal_point
            case "down":
                dist, direction = self.get_camera_to_focal_distance()
                if dist > self.get_gimble_limit() or (
                    dist < self.get_gimble_limit() and direction == 1
                ):
                    self.camera.pan(0, -val, 0)
                    self.camera.focal_point = focal_point

        if self.always_point_up:
            up = up_dirs_vector[self.settings["scene.up_direction"]]
            self.camera.view_up = up

        self.queue_render()

    def set_view_up(self, direction):
        if self.camera is None:
            return
        self.camera.view_up = direction
        self.queue_render()

    def set_camera_state(self, state):
        if self.camera is None:
            return
        self.camera.state = state
        self.queue_render()

    def get_camera_state(self):
        if self.camera is None:
            return None
        return self.camera.state

    def _pointer_modifiers(self, controller):
        """Return (shift, ctrl, alt) from the current event, if any."""
        try:
            state = controller.get_current_event_state()
        except Exception:
            return False, False, False
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(state & Gdk.ModifierType.ALT_MASK)
        return shift, ctrl, alt

    def _pref_toggled_by_alt(self, enabled: bool, alt: bool) -> bool:
        """Alt temporarily flips a cursor-pivot preference."""
        return bool(enabled) != bool(alt)

    def _scroll_is_touchpad(self, controller):
        """True when scroll comes from a touchpad/surface (not a mouse wheel)."""
        get_unit = getattr(controller, "get_unit", None)
        if get_unit is not None:
            try:
                if get_unit() == Gdk.ScrollUnit.SURFACE:
                    return True
            except Exception as exc:
                if self.logger:
                    self.logger.debug("scroll unit probe failed: %s", exc)
        # Fallback when ScrollUnit is unavailable or misreported.
        try:
            event = controller.get_current_event()
            device = event.get_device() if event is not None else None
            if device is not None and device.get_source() == Gdk.InputSource.TOUCHPAD:
                return True
        except Exception as exc:
            if self.logger:
                self.logger.debug("scroll device probe failed: %s", exc)
        return False

    def apply_nav_settings(self, settings: dict) -> None:
        """Apply navigation prefs from WindowSettings / gschema."""
        if "nav-invert-x" in settings:
            self.nav_invert_x = bool(settings["nav-invert-x"])
        if "nav-invert-y" in settings:
            self.nav_invert_y = bool(settings["nav-invert-y"])
        if "nav-zoom-to-cursor" in settings:
            self.nav_zoom_to_cursor = bool(settings["nav-zoom-to-cursor"])
        if "nav-orbit-around-cursor" in settings:
            self.nav_orbit_around_cursor = bool(settings["nav-orbit-around-cursor"])
        if "nav-touchpad-orbit" in settings:
            self.nav_touchpad_orbit = bool(settings["nav-touchpad-orbit"])
        if "nav-mmb-click-pivot" in settings:
            self.nav_mmb_click_pivot = bool(settings["nav-mmb-click-pivot"])
        if "nav-orbit-sensitivity" in settings:
            self.nav_orbit_sensitivity = clamp_sensitivity(
                settings["nav-orbit-sensitivity"]
            )
        if "nav-zoom-sensitivity" in settings:
            self.nav_zoom_sensitivity = clamp_sensitivity(
                settings["nav-zoom-sensitivity"]
            )
        if "nav-pan-sensitivity" in settings:
            self.nav_pan_sensitivity = clamp_sensitivity(settings["nav-pan-sensitivity"])

    def _nav_mode(self, *, shift, ctrl, touchpad):
        """
        Blender-like viewport navigation.

        Middle-mouse / touchpad two-finger / LMB drag:
          none  → orbit (touchpad/LMB) or zoom (mouse wheel)
          Shift → pan
          Ctrl  → zoom
        Alt (with orbit/zoom) → pivot about view center, not under cursor.
        Double-click LMB → classic reset to bounds.
        """
        if shift:
            return "pan"
        if ctrl:
            return "zoom"
        if touchpad and self.nav_touchpad_orbit:
            return "orbit"
        return "zoom"

    def _event_widget_xy(self, controller):
        """Pointer position in widget coordinates (GTK top-left)."""
        try:
            event = controller.get_current_event()
            if event is not None:
                pos = event.get_position()
                if isinstance(pos, tuple) and len(pos) >= 2:
                    return float(pos[0]), float(pos[1])
        except Exception as exc:
            if self.logger:
                self.logger.debug("event position probe failed: %s", exc)
        # Prefer center when we never saw motion — corner pivots are unstable.
        if self._pointer_xy == (0.0, 0.0) and self.width > 1 and self.height > 1:
            return self.width * 0.5, self.height * 0.5
        return self._pointer_xy

    def _world_under_pointer(self, x: float, y: float):
        """
        World point under the cursor on the current focal plane.

        Uses F3D ``get_display_from_world`` / ``get_world_from_display`` so zoom
        and orbit respect click/pointer location (no mesh picker required).
        """
        if self.window is None or self.camera is None:
            return None
        try:
            scale = float(self.get_scale_factor())
            dx, dy = gtk_to_display(x, y, self.height, scale)
            foc = tuple(self.camera.focal_point)
            pos = tuple(self.camera.position)
            foc_disp = self.window.get_display_from_world(foc)
            world = tuple(self.window.get_world_from_display((dx, dy, foc_disp[2])))
            if not is_sane_pivot(world, pos, foc):
                return None
            return world
        except Exception as exc:
            if self.logger:
                self.logger.debug("world_under_pointer failed: %s", exc)
            return None

    def _elevation_gimbal_allows(self, elevation_deg: float) -> bool:
        dist, direction = self.get_camera_to_focal_distance()
        limit = self.get_gimble_limit()
        if dist > limit:
            return True
        if direction == 1 and elevation_deg < 0:
            return True
        if direction == -1 and elevation_deg > 0:
            return True
        return False

    def _apply_orbit_delta(self, azimuth_deg, elevation_deg):
        """Orbit around the current focal point (legacy / fallback)."""
        if not self.always_point_up:
            self.camera.elevation(elevation_deg)
            self.camera.azimuth(azimuth_deg)
            return
        if self._elevation_gimbal_allows(elevation_deg):
            self.camera.elevation(elevation_deg)
        self.camera.azimuth(azimuth_deg)

    def _apply_orbit_at(
        self,
        azimuth_deg,
        elevation_deg,
        x: float,
        y: float,
        *,
        around_cursor: bool | None = None,
    ):
        """
        Orbit the camera.

        Classic Exhibit (default): pivot = focal point — model stays centered.
        Cursor mode: pivot under pointer (model can leave screen center).
        """
        az = axis_delta(
            azimuth_deg, invert=self.nav_invert_x, sensitivity=self.nav_orbit_sensitivity
        )
        el = axis_delta(
            elevation_deg,
            invert=self.nav_invert_y,
            sensitivity=self.nav_orbit_sensitivity,
        )
        # Soft per-event angle cap after sensitivity.
        az = max(-15.0, min(15.0, az))
        el = max(-15.0, min(15.0, el))

        if around_cursor is None:
            around_cursor = self.nav_orbit_around_cursor

        pos = tuple(self.camera.position)
        foc = tuple(self.camera.focal_point)
        # Classic: lock orbit on the view/focal center so the model does not drift.
        pivot = foc
        if around_cursor:
            under = self._world_under_pointer(x, y)
            if under is not None:
                pivot = under

        up = up_dirs_vector[self.settings["scene.up_direction"]]

        def gimbal_ok(_pos, _foc):
            if not self.always_point_up:
                return True
            return self._elevation_gimbal_allows(el)

        new_pos, new_foc = orbit_rig_around_pivot(
            pos,
            foc,
            pivot,
            up,
            az,
            el,
            gimbal_ok=gimbal_ok,
        )
        self.camera.position = new_pos
        self.camera.focal_point = new_foc

    def _apply_pan_delta(
        self,
        dx,
        dy,
        x: float | None = None,
        y: float | None = None,
        *,
        use_cursor_depth: bool = True,
    ):
        dx = axis_delta(dx, invert=self.nav_invert_x, sensitivity=self.nav_pan_sensitivity)
        dy = axis_delta(dy, invert=self.nav_invert_y, sensitivity=self.nav_pan_sensitivity)
        dist = self.distance
        if use_cursor_depth and x is not None and y is not None:
            under = self._world_under_pointer(x, y)
            if under is not None:
                dist = depth_distance(tuple(self.camera.position), under)
        scale = pan_scale_for_distance(dist, self.width)
        self.camera.pan(dx * scale, dy * scale, 0)

    def _apply_zoom_delta(
        self,
        dy,
        x: float | None = None,
        y: float | None = None,
        *,
        to_cursor: bool | None = None,
    ):
        dy = axis_delta(dy, invert=self.nav_invert_y, sensitivity=self.nav_zoom_sensitivity)
        factor = clamp_dolly_factor(1 - 0.1 * dy)
        if abs(factor - 1.0) < 1e-12:
            return
        if self.settings.get("scene.camera.orthographic"):
            self.camera.zoom(factor)
            self.get_distance()
            return

        if to_cursor is None:
            to_cursor = self.nav_zoom_to_cursor
        use_cursor = to_cursor and x is not None and y is not None
        cursor = self._world_under_pointer(x, y) if use_cursor else None
        if cursor is None:
            self.camera.dolly(factor)
            self.get_distance()
            return

        pos = tuple(self.camera.position)
        foc = tuple(self.camera.focal_point)
        new_pos, new_foc = dolly_to_cursor(pos, foc, factor, cursor)
        self.camera.position = new_pos
        self.camera.focal_point = new_foc
        self.get_distance()

    def _recenter_on_pointer(self, x: float, y: float) -> bool:
        """Set orbit center to the focal-plane point under the cursor (F3D MMB click)."""
        if not self.nav_mmb_click_pivot:
            return False
        pivot = self._world_under_pointer(x, y)
        if pivot is None:
            return False
        pos = tuple(self.camera.position)
        foc = tuple(self.camera.focal_point)
        new_pos, new_foc = pivot_camera_to_point(pos, foc, pivot, keep_camera_plane=True)
        self.camera.position = new_pos
        self.camera.focal_point = new_foc
        self.get_distance()
        return True

    def _notify_camera_changed(self) -> None:
        cb = self.camera_changed_cb
        if not callable(cb):
            return
        try:
            cb(self)
        except Exception as exc:
            if self.logger:
                self.logger.debug("camera_changed_cb failed: %s", exc)

    def _finalize_camera_nav(self):
        if self.always_point_up:
            up = up_dirs_vector[self.settings["scene.up_direction"]]
            self.camera.view_up = up
        self.queue_render()
        self._notify_camera_changed()

    @Gtk.Template.Callback("on_pointer_motion")
    def on_pointer_motion(self, _controller, x, y):
        self._pointer_xy = (float(x), float(y))

    @Gtk.Template.Callback("on_scroll")
    def on_scroll(self, gesture, dx, dy):
        if self.camera is None:
            return False

        shift, ctrl, alt = self._pointer_modifiers(gesture)
        touchpad = self._scroll_is_touchpad(gesture)
        mode = self._nav_mode(shift=shift, ctrl=ctrl, touchpad=touchpad)
        around = self._pref_toggled_by_alt(self.nav_orbit_around_cursor, alt)
        to_cursor = self._pref_toggled_by_alt(self.nav_zoom_to_cursor, alt)
        use_cursor_depth = self._pref_toggled_by_alt(True, alt)
        x, y = self._event_widget_xy(gesture)
        dx, dy = clamp_scroll_delta(dx, dy, touchpad=touchpad)

        # SURFACE deltas are pixel-like; WHEEL notches are ~±1.
        if mode == "pan":
            if touchpad:
                self._apply_pan_delta(
                    -dx, dy, x, y, use_cursor_depth=use_cursor_depth
                )
            else:
                self._apply_pan_delta(
                    -dx * 40.0,
                    dy * 40.0,
                    x,
                    y,
                    use_cursor_depth=use_cursor_depth,
                )
        elif mode == "orbit":
            # Two-finger swipe ≈ Blender middle-mouse orbit (low gain).
            if touchpad:
                self._apply_orbit_at(
                    -dx * 0.15, dy * 0.15, x, y, around_cursor=around
                )
            else:
                self._apply_orbit_at(
                    -dx * 8.0, dy * 8.0, x, y, around_cursor=around
                )
        else:
            self._apply_zoom_delta(
                dy * 0.05 if touchpad else dy, x, y, to_cursor=to_cursor
            )

        self._finalize_camera_nav()
        return True

    @Gtk.Template.Callback("on_zoom_scale_changed")
    def on_zoom_scale_changed(self, zoom_gesture, scale):
        if self.camera is None:
            return
        _shift, _ctrl, alt = self._pointer_modifiers(zoom_gesture)
        to_cursor = self._pref_toggled_by_alt(self.nav_zoom_to_cursor, alt)
        x, y = self._pointer_xy
        factor = clamp_dolly_factor(1 - self.prev_scale + scale)
        if abs(factor - 1.0) > 1e-12:
            # Map pinch factor into zoom-delta space used by _apply_zoom_delta.
            dy = (1.0 - factor) / 0.1
            self._apply_zoom_delta(dy, x, y, to_cursor=to_cursor)
        self.prev_scale = scale
        self._finalize_camera_nav()

    @Gtk.Template.Callback("on_click_pressed")
    def on_click_pressed(self, gesture, n_press, x, y):
        # Classic F3D/viewer: double-click LMB frames the model (reset to bounds).
        if n_press != 2 or self.camera is None:
            return
        self._pointer_xy = (float(x), float(y))
        self.reset_to_bounds()

    @Gtk.Template.Callback("on_drag_begin")
    def on_drag_begin(self, gesture, x, y):
        self.drag_prev_offset = (0, 0)
        self._drag_start_xy = (float(x), float(y))
        self._pointer_xy = (float(x), float(y))
        self._drag_moved = False
        self._drag_button = gesture.get_current_button()
        shift, ctrl, alt = self._pointer_modifiers(gesture)
        # Stored for the whole drag so Alt state at press decides pivot mode.
        self._drag_orbit_around_cursor = self._pref_toggled_by_alt(
            self.nav_orbit_around_cursor, alt
        )
        self._drag_zoom_to_cursor = self._pref_toggled_by_alt(
            self.nav_zoom_to_cursor, alt
        )
        self._drag_use_cursor_depth = self._pref_toggled_by_alt(True, alt)
        if self._drag_button == 2:
            self._drag_mode = "zoom" if (ctrl and not shift) else "pan"
        else:
            self._drag_mode = self._nav_mode(shift=shift, ctrl=ctrl, touchpad=True)

    @Gtk.Template.Callback("on_drag_update")
    def on_drag_update(self, gesture, x_offset, y_offset):
        if self.camera is None:
            return

        dx = self.drag_prev_offset[0] - x_offset
        dy = self.drag_prev_offset[1] - y_offset
        if abs(x_offset) > self._click_drag_threshold or abs(y_offset) > self._click_drag_threshold:
            self._drag_moved = True

        px = self._drag_start_xy[0] + x_offset
        py = self._drag_start_xy[1] + y_offset
        self._pointer_xy = (px, py)
        mode = self._drag_mode

        if self._drag_button == 1 or self._drag_button == 2:
            if mode == "pan":
                # GTK y grows down; camera pan y grows up.
                self._apply_pan_delta(
                    dx,
                    -dy,
                    px,
                    py,
                    use_cursor_depth=self._drag_use_cursor_depth,
                )
            elif mode == "zoom":
                self._apply_zoom_delta(
                    dy * 0.05,
                    px,
                    py,
                    to_cursor=self._drag_zoom_to_cursor,
                )
            else:
                # Natural: drag right → +azimuth; drag down → +elevation.
                # Invert X/Y settings flip via axis_delta inside.
                self._apply_orbit_at(
                    dx * 0.5,
                    dy * 0.5,
                    px,
                    py,
                    around_cursor=self._drag_orbit_around_cursor,
                )

        self._finalize_camera_nav()
        self.drag_prev_offset = (x_offset, y_offset)

    @Gtk.Template.Callback("on_drag_end")
    def on_drag_end(self, gesture, *args):
        # MMB click without drag: new orbit center under cursor (F3D).
        # Classic frame-all is double-click LMB (see on_click_pressed).
        if (
            self.camera is not None
            and not self._drag_moved
            and self._drag_button == 2
        ):
            x, y = self._drag_start_xy
            if self._recenter_on_pointer(x, y):
                self._finalize_camera_nav()
        self.drag_prev_offset = (0, 0)
        self._drag_moved = False

    def create_action(self, name, callback, *args):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback, *args)
        self.action_group.add_action(action)
        return action

