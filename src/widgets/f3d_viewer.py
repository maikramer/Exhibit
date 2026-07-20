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

from ..camera_views import UP_DIRS, apply_view
from ..vector_math import p_dist, v_abs, v_add, v_sub, v_mul, v_dot_p
from .. import logger_lib
from ..meshopt_decompress import (
    MeshoptError,
    cleanup_decompressed,
    prepare_glb_for_load,
    release_prepared,
)
from ..gltf_scene_graph import (
    ScenePart,
    SceneTreeNode,
    _effective_hidden,
    _load_gltf,
    build_glb_hiding_nodes_bytes,
    build_scene_tree,
    list_mesh_parts,
)


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
class F3DViewer(Gtk.GLArea):
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
        "scalar": "model.scivis.array_name",  # rename to scivis-name
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

        self.always_point_up = True

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
        return upper

    @GObject.Property(type=float)
    def lower_time_range(self):
        if self.scene is None:
            return 0.0
        lower, _upper = self.scene.animation_time_range()
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
            except Exception:
                pass

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
        self.camera.reset_to_bounds()
        self.get_distance()
        self.queue_render()

    def front_view(self, *args):
        apply_view(self.camera, "front", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()

    def right_view(self, *args):
        apply_view(self.camera, "right", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()

    def back_view(self, *args):
        apply_view(self.camera, "back", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()

    def left_view(self, *args):
        apply_view(self.camera, "left", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()

    def top_view(self, *args):
        apply_view(self.camera, "top", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()

    def isometric_view(self, *args):
        apply_view(self.camera, "isometric", self.settings["scene.up_direction"])
        self.get_distance()
        self.queue_render()

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
        if key == "animation-index" and not isinstance(value, (list, tuple)):
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
        except Exception:
            return []

    def _clear_force_reader(self) -> None:
        """Unset optional ``scene.force_reader`` (Python lacks options.reset)."""
        if not self.engine:
            return
        opts = self.engine.options
        if "scene.force_reader" not in opts:
            return
        reset = getattr(opts, "reset", None) or getattr(opts, "remove_value", None)
        if callable(reset):
            try:
                reset("scene.force_reader")
                return
            except Exception:
                pass
        kept = {key: opts[key] for key in list(opts.keys()) if key != "scene.force_reader"}
        fresh = f3d.Options()
        for key, value in kept.items():
            try:
                fresh[key] = value
            except Exception:
                pass
        self.engine.options = fresh
        if self.settings:
            try:
                self.engine.options.update(self.settings)
            except Exception:
                pass

    def _add_scene_buffer(self, data: bytes, *, reader: str = "GLB") -> None:
        """
        Load geometry from an in-memory buffer (F3D ``scene.add(bytes)``).

        VTK builds older than 9.6.20260128 need ``scene.force_reader``.
        """
        if not self.scene or not self.engine:
            raise RuntimeError("Viewer engine is not ready")

        try:
            self.scene.add(data)
            return
        except Exception:
            pass

        self.engine.options["scene.force_reader"] = reader
        try:
            self.scene.add(data)
        finally:
            self._clear_force_reader()

    def render_image(self):
        self.get_context().make_current()
        img = self.window.render_to_image()
        # print(img.to_terminal_text())
        return img

    def supports(self, filepath):
        return self.scene.supports(filepath)

    def _prepare_filepath(self, filepath):
        try:
            return prepare_glb_for_load(filepath)
        except MeshoptError as e:
            self.logger.error(f"Error while decompressing meshopt GLB: {e}")
            return None, None

    def _resolve_load_path(self, filepath, prepared_path=None):
        """Return path ready for F3D. Prefer caller-prepared path (single owner)."""
        if prepared_path:
            return prepared_path, None
        return self._prepare_filepath(filepath)

    def _release_prepared_path(self) -> None:
        previous = self._prepared_path
        self._prepared_path = None
        if previous and previous != self._loaded_filepath:
            release_prepared(previous)

    def release_resources(self) -> None:
        """Stop timers, clear scene, drop engine + prepare temps (tab close)."""
        self._playing = False
        self._stop_animation_timer()
        try:
            self.set_auto_render(False)
        except Exception:
            pass

        # Make GL current so VTK/F3D can free GPU-side resources.
        try:
            if self.get_realized():
                self.make_current()
        except Exception:
            pass

        if self.scene is not None:
            try:
                self.scene.clear()
            except Exception:
                pass

        self._release_prepared_path()
        self._loaded_filepath = None
        self._hidden_part_indices = set()

        # Drop native F3D/VTK refs so GPU/RAM can be reclaimed.
        engine = self.engine
        self.camera = None
        self.window = None
        self.scene = None
        self.engine = None
        del engine

    def load_file(self, filepath, prepared_path=None):
        hdri_ambient = bool(self.settings.get("render.hdri.ambient"))
        if hdri_ambient and self.engine:
            self.engine.options.update({"render.hdri.ambient": False})

        # prepare_glb_for_load retains cache temps; drop duplicate if we already hold it.
        if (
            prepared_path
            and prepared_path == self._prepared_path
            and prepared_path != filepath
        ):
            release_prepared(prepared_path)

        previous_prepared = self._prepared_path
        self.scene.clear()
        self._hidden_part_indices = set()

        load_path, meshopt_temp = self._resolve_load_path(filepath, prepared_path)
        if load_path is None:
            self._loaded_filepath = None
            self._prepared_path = None
            if previous_prepared and previous_prepared != filepath:
                release_prepared(previous_prepared)
            return False

        try:
            self.scene.add(load_path)
        except Exception as e:
            self.logger.error(f"Error while loading file: {e}")
            self._loaded_filepath = None
            self._prepared_path = None
            if previous_prepared and previous_prepared != load_path:
                release_prepared(previous_prepared)
            if load_path != filepath and load_path != previous_prepared:
                release_prepared(load_path)
            return False
        finally:
            cleanup_decompressed(meshopt_temp)

        self._loaded_filepath = filepath
        self._prepared_path = load_path
        if previous_prepared and previous_prepared != load_path:
            release_prepared(previous_prepared)
        self.notify("lower-time-range")
        self.notify("upper-time-range")
        self.queue_render()

        return True

    def add_file(self, filepath, prepared_path=None):
        if self.settings.get("render.hdri.ambient") and self.engine:
            self.engine.options.update({"render.hdri.ambient": False})

        load_path, meshopt_temp = self._resolve_load_path(filepath, prepared_path)
        if load_path is None:
            return False

        try:
            self.scene.add(load_path)
        except Exception as e:
            self.logger.error(f"Error while loading file: {e}")
            if load_path != filepath:
                release_prepared(load_path)
            return False
        finally:
            cleanup_decompressed(meshopt_temp)

        previous_prepared = self._prepared_path
        self._loaded_filepath = filepath
        self._prepared_path = load_path
        if previous_prepared and previous_prepared != load_path:
            release_prepared(previous_prepared)
        self.notify("lower-time-range")
        self.notify("upper-time-range")

        self.get_distance()
        self.queue_render()

        return True

    def get_scene_parts(self) -> list[ScenePart]:
        path = self._prepared_path or self._loaded_filepath
        if not path:
            return []
        return list_mesh_parts(path, already_prepared=bool(self._prepared_path))

    def get_scene_tree(self) -> list[SceneTreeNode]:
        path = self._prepared_path or self._loaded_filepath
        if not path:
            return []
        return build_scene_tree(path, already_prepared=bool(self._prepared_path))

    def get_hidden_part_indices(self) -> set[int]:
        return set(self._hidden_part_indices)

    def get_effective_hidden_part_indices(self) -> set[int]:
        """Hidden set expanded so descendants of a hidden ancestor stay hidden."""
        explicit = set(self._hidden_part_indices)
        if not explicit:
            return explicit
        path = self._prepared_path or self._loaded_filepath
        if not path:
            return explicit
        gltf = _load_gltf(path, already_prepared=bool(self._prepared_path))
        if not gltf:
            return explicit
        nodes = gltf.get("nodes") or []
        if not isinstance(nodes, list):
            return explicit
        return _effective_hidden(nodes, explicit)

    def get_prepared_path(self) -> str | None:
        """Path currently prepared for F3D (may equal the source file)."""
        return self._prepared_path or self._loaded_filepath

    def set_part_visible(self, node_index: int, visible: bool) -> bool:
        """Show/hide a mesh node. Returns False if the scene could not be updated."""
        if not self._loaded_filepath:
            return False

        previous_hidden = set(self._hidden_part_indices)
        if visible:
            self._hidden_part_indices.discard(int(node_index))
        else:
            self._hidden_part_indices.add(int(node_index))

        if not self._reload_with_part_visibility():
            self._hidden_part_indices = previous_hidden
            return False
        return True

    def _reload_with_part_visibility(self) -> bool:
        """
        Reimport scene with hidden meshes stripped from GLB JSON.

        Native per-actor hide needs F3D ``ui.scene_hierarchy`` (MODULE_UI).
        Meanwhile clear+add with an in-memory filtered GLB avoids temp files.
        """
        filepath = self._loaded_filepath
        prepared = self._prepared_path
        if not filepath:
            return False

        camera_state = None
        if self.camera is not None:
            try:
                camera_state = self.get_camera_state()
            except Exception:
                camera_state = None

        anim_time = self._animation_time
        was_playing = self._playing
        self.playing = False

        hdri_ambient = bool(self.settings.get("render.hdri.ambient"))
        if hdri_ambient and self.engine:
            self.engine.options.update({"render.hdri.ambient": False})

        restore_path = prepared or filepath
        load_buffer: bytes | None = None
        load_path: str | None = None
        try:
            if self._hidden_part_indices:
                load_buffer = build_glb_hiding_nodes_bytes(
                    filepath,
                    self._hidden_part_indices,
                    prepared_path=prepared,
                )
            else:
                # Restore full scene from the prepared path (no re-prepare).
                if prepared:
                    load_path = prepared
                else:
                    load_path, prep_temp = self._prepare_filepath(filepath)
                    if load_path is None:
                        return False
                    self._prepared_path = load_path
                    restore_path = load_path

            # Build filtered GLB before clearing so a failure keeps the scene.
            self.scene.clear()
            try:
                if load_buffer is not None:
                    self._add_scene_buffer(load_buffer)
                else:
                    self.scene.add(load_path)
            except Exception:
                # Best-effort restore of the previous full scene.
                try:
                    self.scene.add(restore_path)
                except Exception:
                    pass
                raise
        except Exception as e:
            self.logger.error(f"Error while updating part visibility: {e}")
            return False

        self.notify("lower-time-range")
        self.notify("upper-time-range")

        lower = self.lower_time_range
        upper = self.upper_time_range
        if anim_time < lower or anim_time > upper:
            anim_time = lower
        self.animation_time = anim_time

        if camera_state is not None:
            try:
                self.set_camera_state(camera_state)
            except Exception:
                pass

        if was_playing:
            self.playing = True

        self.queue_render()
        return True

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

    @Gtk.Template.Callback("on_scroll")
    def on_scroll(self, gesture, dx, dy):
        if self.settings["scene.camera.orthographic"]:
            self.camera.zoom(1 - 0.1 * dy)
        else:
            self.camera.dolly(1 - 0.1 * dy)
        self.get_distance()
        self.queue_render()

    @Gtk.Template.Callback("on_zoom_scale_changed")
    def on_zoom_scale_changed(self, zoom_gesture, scale):
        self.camera.dolly(1 - self.prev_scale + scale)
        self.prev_scale = scale
        self.get_distance()
        self.queue_render()

    @Gtk.Template.Callback("on_drag_update")
    def on_drag_update(self, gesture, x_offset, y_offset):
        if gesture.get_current_button() == 1:
            dist, direction = self.get_camera_to_focal_distance()
            y = -(self.drag_prev_offset[1] - y_offset) * 0.5
            x = (self.drag_prev_offset[0] - x_offset) * 0.5
            if not self.always_point_up:
                self.camera.elevation(y)
                self.camera.azimuth(x)
            else:
                if (
                    dist > self.get_gimble_limit()
                    or (dist < self.get_gimble_limit())
                    and (direction == 1 and y < 0)
                    or (dist < self.get_gimble_limit() and direction == -1 and y > 0)
                ):
                    self.camera.elevation(y)
                self.camera.azimuth(x)
        elif gesture.get_current_button() == 2:
            self.camera.pan(
                (self.drag_prev_offset[0] - x_offset)
                * (0.0000001 * self.width + 0.001 * self.distance),
                -(self.drag_prev_offset[1] - y_offset)
                * (0.0000001 * self.height + 0.001 * self.distance),
                0,
            )

        if self.always_point_up:
            up = up_dirs_vector[self.settings["scene.up_direction"]]
            self.camera.view_up = up

        self.queue_render()

        self.drag_prev_offset = (x_offset, y_offset)

    @Gtk.Template.Callback("on_drag_end")
    def on_drag_end(self, gesture, *args):
        self.drag_prev_offset = (0, 0)

    def create_action(self, name, callback, *args):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback, *args)
        self.action_group.add_action(action)
        return action

