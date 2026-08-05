# f3d_viewer.py — compatibility shim over Exb.View during libexhibit migration
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import os
from typing import Any

from gi.repository import Exb, Gdk, Gio, GLib, GObject, Gtk

import tempfile

from ..gltf_scene_graph import (
    ScenePart,
    SceneTreeNode,
    build_glb_hiding_nodes_bytes,
    build_scene_tree,
    list_mesh_parts,
)
from ..meshopt_decompress import (
    _read_glb_json,
    is_adhoc_load_temp,
    prepare_glb_for_load,
    release_load_temp,
    release_prepared,
)

log = logging.getLogger(__name__)


def _as_rgba(value) -> Gdk.RGBA | None:
    if isinstance(value, Gdk.RGBA):
        return value
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        rgba = Gdk.RGBA()
        rgba.red = float(value[0])
        rgba.green = float(value[1])
        rgba.blue = float(value[2])
        rgba.alpha = float(value[3]) if len(value) > 3 else 1.0
        return rgba
    return None


def resolve_sprites_nick(options: dict) -> str | None:
    """Map view options → Exb.Sprites nick, or None if sprite keys absent.

    ``sprite-enabled=False`` always wins over ``sprites-type`` (defaults keep
    type=sphere while disabled; full ``get_view_settings()`` sync must not
    turn meshes into point spheres).
    """
    if "sprite-enabled" not in options and "sprites-type" not in options:
        return None
    if options.get("sprite-enabled") is False:
        return "NONE"
    typ = options.get("sprites-type")
    if typ is not None:
        return str(typ).replace("-", "_").upper()
    if options.get("sprite-enabled") is True:
        return "SPHERE"
    return None


_UP_TO_EXB = {
    "+X": "POSITIVE_X",
    "-X": "NEGATIVE_X",
    "+Y": "POSITIVE_Y",
    "-Y": "NEGATIVE_Y",
    "+Z": "POSITIVE_Z",
    "-Z": "NEGATIVE_Z",
}


class _EngineOptionsFacade:
    """Minimal stand-in for ``f3d.Engine.options`` used by InspectMixin."""

    def __init__(self, viewer: "F3DViewer"):
        self._viewer = viewer

    def update(self, options: dict) -> None:
        if not options:
            return
        self._viewer.update_options(options)


class F3DViewer(Gtk.Box):
    """Fork-facing viewer API backed by ``Exb.View`` / ``Exb.Engine``.

    Advanced F3D-Python features are stubbed until re-ported onto libexhibit.
    """

    def __init__(self, *args, view: Exb.View | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_orientation(Gtk.Orientation.VERTICAL)
        if view is not None:
            self.view = view
            self.engine = view.get_engine()
            # Bridge mode: do not reparent the template view into this box.
            self._bridge = True
        else:
            # engine is CONSTRUCT_ONLY — bare Exb.View() leaves engine=NULL.
            self.engine = Exb.Engine.new()
            self.view = Exb.View(engine=self.engine)
            self.view.set_hexpand(True)
            self.view.set_vexpand(True)
            self.append(self.view)
            self._bridge = False
        self.settings: dict | None = None
        self.logger = log
        self.scene = None
        # Current on-disk path fed to Exb (may be hide/skin adhoc temp).
        self._prepared_path: str | None = None
        # Stable prepare-cache path (never exhibit-hide-/skinw- temps).
        self._base_prepared_path: str | None = None
        self._loaded_filepath: str | None = None
        self._options_batch = 0
        self._nav_settings: dict = {}
        self._hidden_parts: set[int] = set()
        self._scene_tree: list[SceneTreeNode] = []
        self._scene_parts: list[ScenePart] = []
        self._animation_time = 0.0
        self._lower_time_range = 0.0
        self._upper_time_range = 1.0
        self._playing = False
        self._anim_end_handler_id = 0
        # Match Exb.View default (turntable / orbit-with-limit).
        self._always_point_up = True
        self._fit_camera_on_done = True
        self.camera_changed_cb = None
        self._camera_cb_idle = 0
        # Fork InspectMixin uses engine.options.update(...); provide a facade.
        self.options = _EngineOptionsFacade(self)
        try:
            self.engine.options = self.options
        except Exception:
            pass
        try:
            self.engine.connect("changed", self._on_engine_changed)
        except Exception as exc:
            log.debug("engine changed connect: %s", exc)

    def _on_engine_changed(self, *_args) -> None:
        """Coalesce Exb.Engine::changed → camera_changed_cb (sync / split)."""
        if self.camera_changed_cb is None:
            return
        if self._camera_cb_idle:
            return

        def _emit() -> bool:
            self._camera_cb_idle = 0
            cb = self.camera_changed_cb
            if cb is not None:
                try:
                    cb(self)
                except Exception as exc:
                    log.debug("camera_changed_cb: %s", exc)
            return GLib.SOURCE_REMOVE

        self._camera_cb_idle = GLib.idle_add(_emit)

    def get_view(self) -> Exb.View:
        return self.view

    def initialize(self) -> None:
        """No-op: Exb.View/Engine exist at construction (legacy F3D create_external)."""
        return

    def get_realized(self) -> bool:
        try:
            return bool(self.view.get_realized())
        except Exception:
            # Fail closed — warm-load must wait, not race Exb deferred load.
            return False

    def queue_render(self) -> None:
        try:
            self.view.queue_render()
        except Exception as exc:
            log.debug("queue_render: %s", exc)

    def update_options(self, options: dict, *, queue_render: bool = True) -> None:
        if not options:
            return
        eng = self.engine
        mapping = {
            "orthographic": "orthographic",
            "grid": "show-grid",
            "grid-absolute": "grid-absolute",
            "show-edges": "show-edges",
            "edge-enable": "show-edges",
            "edges-width": "edges-width",
            "point-size": "point-size",
            "armature-enable": "show-armature",
            "show-armature": "show-armature",
            "tone-mapping": "tone-mapping",
            "ambient-occlusion": "ambient-occlusion",
            "bloom": "bloom",
            "bloom-threshold": "bloom-threshold",
            "bloom-intensity": "bloom-intensity",
            "bloom-radius": "bloom-radius",
            "godrays": "godrays",
            "godrays-intensity": "godrays-intensity",
            "godrays-decay": "godrays-decay",
            "godrays-density": "godrays-density",
            "godrays-weight": "godrays-weight",
            "ao-radius": "ao-radius",
            "ao-bias": "ao-bias",
            "ao-kernel-size": "ao-kernel-size",
            "ao-intensity": "ao-intensity",
            "hdri-ambient": "hdri-ambient",
            "hdri-skybox": "hdri-skybox",
            "blur-background": "blur-background",
            "blur-coc": "blur-coc",
            "volume": "volume-rendering",
            "inverse": "volume-inverse-opacity",
            "animation-index": "animation-index",
            "model-opacity": "model-opacity",
            "model-metallic": "model-metallic",
            "model-roughness": "model-roughness",
            "light-intensity": "light-intensity",
            "scivis-array-name": "scivis-array-name",
            "scalar": "scivis-array-name",
            "scivis-enabled": "scivis",
            "scivis": "scivis",
            "scivis-component": "scivis-component",
            "scivis-cells": "scivis-cells",
            "cells": "scivis-cells",
            "checkerboard-enable": "model-checkerboard",
            "model-checkerboard": "model-checkerboard",
            "display-depth": "display-depth",
            "normal-glyphs": "normal-glyphs",
            "normal-glyphs-scale": "normal-glyphs-scale",
            "model-unlit": "model-unlit",
            "sprites-size": "sprites-size",
        }
        for key, value in options.items():
            if key.startswith("ui.") or key == "scalar-bar":
                # scalar-bar has no Exb prop yet (F3D ui.scalar_bar).
                continue
            if key in ("bg-color", "model-color", "grid-color"):
                prop = {
                    "bg-color": "background-color",
                    "model-color": "model-color",
                    "grid-color": "grid-color",
                }[key]
                try:
                    rgba = _as_rgba(value)
                    if rgba is not None:
                        eng.set_property(prop, rgba)
                except Exception as exc:
                    log.debug("update_options %s: %s", key, exc)
                continue
            if key == "hdri-file":
                try:
                    if not value:
                        eng.set_property("hdri-file", None)
                    elif isinstance(value, Gio.File):
                        eng.set_property("hdri-file", value)
                    else:
                        eng.set_property(
                            "hdri-file", Gio.File.new_for_path(str(value))
                        )
                except Exception as exc:
                    log.debug("update_options hdri-file: %s", exc)
                continue
            if key == "animation-time":
                # WindowSettings / presets use seconds; Exb adj is ms.
                try:
                    self.animation_time = float(value)
                except Exception as exc:
                    log.debug("update_options animation-time: %s", exc)
                continue
            if key == "up":
                # Exb uses Exb.Direction enum; WindowSettings keeps "+Y" strings.
                try:
                    enum_name = _UP_TO_EXB.get(str(value), "POSITIVE_Y")
                    eng.set_property("up", getattr(Exb.Direction, enum_name))
                except Exception as exc:
                    log.debug("update_options up: %s", exc)
                continue
            if key in ("model.unlit", "model-unlit"):
                try:
                    eng.set_property("model-unlit", bool(value))
                except Exception as exc:
                    log.debug("update_options model-unlit: %s", exc)
                continue
            if key in ("sprites-type", "sprite-enabled"):
                # Applied once after the loop — order must not re-enable sprites.
                continue
            if key == "anti-aliasing":
                try:
                    if isinstance(value, bool):
                        mode = (
                            Exb.AntiAliasing.FXAA
                            if value
                            else Exb.AntiAliasing.NONE
                        )
                    else:
                        nick = str(value).replace("-", "_").upper()
                        mode = getattr(Exb.AntiAliasing, nick, Exb.AntiAliasing.FXAA)
                    eng.set_property("anti-aliasing", mode)
                except Exception as exc:
                    log.debug("update_options anti-aliasing: %s", exc)
                continue
            if key == "translucency-support":
                # Preset/config bool → Exb.Blending (DDP vs none).
                try:
                    mode = Exb.Blending.DDP if value else Exb.Blending.NONE
                    eng.set_property("blending", mode)
                except Exception as exc:
                    log.debug("update_options translucency-support: %s", exc)
                continue
            prop = mapping.get(key)
            if prop is None:
                # Allow direct Exb property names (and dotted F3D leftovers).
                dotted = key.replace(".", "-")
                if eng.find_property(key) is not None:
                    prop = key
                elif eng.find_property(dotted) is not None:
                    prop = dotted
                else:
                    prop = None
            if prop is None:
                log.debug("update_options: skip unmapped %s", key)
                continue
            try:
                if prop == "animation-index":
                    # None → empty indices + reimport (VTK keeps last skin pose).
                    # -1 → all clips; >=0 → one clip. Exb uses -2 for empty.
                    if value is None:
                        self.reset_to_bind_pose()
                        continue
                    value = int(value)
                eng.set_property(prop, value)
            except Exception as exc:
                log.debug("update_options %s: %s", key, exc)

        nick = resolve_sprites_nick(options)
        if nick is not None:
            try:
                if nick == "NONE":
                    eng.set_property("sprites", Exb.Sprites.NONE)
                elif (
                    options.get("sprite-enabled") is True
                    and "sprites-type" not in options
                ):
                    # Enable without a type: keep current; default sphere.
                    if eng.get_property("sprites") == Exb.Sprites.NONE:
                        eng.set_property("sprites", Exb.Sprites.SPHERE)
                else:
                    eng.set_property(
                        "sprites", getattr(Exb.Sprites, nick, Exb.Sprites.SPHERE)
                    )
            except Exception as exc:
                log.debug("update_options sprites: %s", exc)

        if queue_render and self._options_batch == 0:
            self.queue_render()

    def begin_options_batch(self) -> None:
        self._options_batch += 1

    def end_options_batch(self) -> None:
        self._options_batch = max(0, self._options_batch - 1)
        if self._options_batch == 0:
            self.queue_render()

    def available_animations(self) -> int:
        try:
            return int(self.engine.get_animations_n())
        except Exception:
            return 0

    def get_animation_names(self) -> list[str]:
        n = self.available_animations()
        names: list[str] = []
        path = self.get_prepared_path() or self._loaded_filepath
        if path and str(path).lower().endswith((".glb", ".gltf")):
            try:
                lower = str(path).lower()
                if lower.endswith(".gltf"):
                    import json

                    with open(path, "r", encoding="utf-8") as handle:
                        gltf = json.load(handle)
                else:
                    gltf = _read_glb_json(path)
                for anim in gltf.get("animations") or []:
                    if isinstance(anim, dict):
                        names.append(str(anim.get("name") or ""))
                    else:
                        names.append("")
            except Exception as exc:
                log.debug("animation names from glTF: %s", exc)
        while len(names) < n:
            names.append("")
        return names[:n] if n else names

    def get_animation_keyframes(self) -> list[float]:
        return []

    @GObject.Property(type=float)
    def animation_time(self) -> float:
        # Public API is seconds; Exb adjustment is milliseconds.
        try:
            adj = self.engine.get_property("animation-adjustment")
            if adj is not None:
                return float(adj.get_value()) / 1000.0
        except Exception:
            pass
        return self._animation_time

    @animation_time.setter
    def animation_time(self, value: float) -> None:
        seconds = float(value)
        self._animation_time = seconds
        try:
            adj = self.engine.get_property("animation-adjustment")
            if adj is not None:
                adj.set_value(seconds * 1000.0)
        except Exception as exc:
            log.debug("animation_time → adjustment: %s", exc)

    @GObject.Property(type=float, default=1.0)
    def upper_time_range(self) -> float:
        return self._upper_time_range

    @upper_time_range.setter
    def upper_time_range(self, value: float) -> None:
        self._upper_time_range = float(value)

    @GObject.Property(type=float, default=0.0)
    def lower_time_range(self) -> float:
        return self._lower_time_range

    @lower_time_range.setter
    def lower_time_range(self, value: float) -> None:
        self._lower_time_range = float(value)

    @GObject.Property(type=bool, default=False)
    def playing(self) -> bool:
        return self._playing

    @playing.setter
    def playing(self, value: bool) -> None:
        want = bool(value)
        changed = want != self._playing
        self._playing = want
        try:
            if self._playing:
                self._watch_animation_end()
                self.engine.play_animation()
            else:
                self._unwatch_animation_end()
                stop = getattr(self.engine, "stop_animation", None)
                if callable(stop):
                    stop()
        except Exception as exc:
            log.debug("play/stop_animation: %s", exc)
        if changed:
            # Custom setter — notify so chrome (notify::playing) resets the icon.
            self.notify("playing")


    def _watch_animation_end(self) -> None:
        """When the clip hits upper, flip playing→False so the chrome icon resets."""
        if self._anim_end_handler_id:
            return
        try:
            adj = self.engine.get_property("animation-adjustment")
        except Exception:
            return
        if adj is None:
            return
        self._anim_end_handler_id = adj.connect(
            "value-changed", self._on_animation_adj_end
        )

    def _unwatch_animation_end(self) -> None:
        hid = self._anim_end_handler_id
        self._anim_end_handler_id = 0
        if not hid:
            return
        try:
            adj = self.engine.get_property("animation-adjustment")
            if adj is not None:
                adj.disconnect(hid)
        except Exception as exc:
            log.debug("unwatch animation-adjustment: %s", exc)

    def _on_animation_adj_end(self, adj) -> None:
        if not self._playing:
            return
        try:
            if float(adj.get_value()) + 1e-3 >= float(adj.get_upper()):
                self.playing = False
        except Exception as exc:
            log.debug("animation end watch: %s", exc)

    @GObject.Property(type=bool, default=False)
    def orthographic(self) -> bool:
        try:
            return bool(self.engine.get_property("orthographic"))
        except Exception:
            return False

    @orthographic.setter
    def orthographic(self, value: bool) -> None:
        try:
            self.engine.set_property("orthographic", bool(value))
        except Exception as exc:
            log.debug("orthographic: %s", exc)

    @GObject.Property(type=bool, default=True)
    def always_point_up(self) -> bool:
        try:
            return bool(self.view.get_property("always-point-up"))
        except Exception:
            return self._always_point_up

    @always_point_up.setter
    def always_point_up(self, value: bool) -> None:
        self._always_point_up = bool(value)
        try:
            self.view.set_property("always-point-up", self._always_point_up)
        except Exception as exc:
            log.debug("always_point_up: %s", exc)

    def set_view_up(self, vec) -> None:
        """Seed engine/view up direction when the property exists."""
        if vec is None:
            return
        for target, prop in (
            (self.engine, "up"),
            (self.view, "up-direction"),
            (self.engine, "up-direction"),
        ):
            try:
                if target.find_property(prop) is not None:
                    target.set_property(prop, vec)
                    return
            except Exception as exc:
                log.debug("set_view_up %s: %s", prop, exc)
        log.debug("set_view_up: no up property for %s", vec)

    def toggle_orthographic(self, *args) -> None:
        self.orthographic = not self.orthographic

    def reset_to_bounds(self) -> None:
        try:
            self.engine.reset_camera()
        except Exception as exc:
            log.debug("reset_camera: %s", exc)

    def reset_to_bind_pose(self) -> bool:
        """Clear clip + reimport so skin returns to bind/rest pose.

        Clearing ``scene.animation.indices`` alone leaves the last posed frame
        (F3D/VTK). Reimport with empty indices restores bind pose; camera kept.
        """
        self.playing = False
        if not self._loaded_filepath:
            try:
                self.engine.set_property("animation-index", -2)
            except Exception:
                pass
            return True
        source = self._base_load_path()
        try:
            if self._hidden_parts and str(source).lower().endswith(
                (".glb", ".gltf")
            ):
                return self._reload_with_part_visibility(clear_animation=True)
            cam = None
            try:
                cam = self.get_camera_state()
            except Exception:
                cam = None
            prepared = self._base_prepared_path
            ok = self.load_file(
                self._loaded_filepath,
                prepared_path=prepared,
                clear_animation=True,
            )
            if ok and cam is not None:
                try:
                    self.set_camera_state(cam)
                except Exception as exc:
                    log.debug("restore camera after bind pose: %s", exc)
            return bool(ok)
        except Exception as exc:
            log.debug("reset_to_bind_pose: %s", exc)
            return False

    def render_image(self):
        try:
            texture = self.engine.render_texture()
        except Exception as exc:
            log.debug("render_texture: %s", exc)
            return None
        if texture is None:
            return None

        class _SaveAdapter:
            """ExportMixin calls ``img.save(path)``; GdkTexture uses save_to_filename."""

            def __init__(self, tex):
                self._tex = tex

            def save(self, path: str) -> None:
                self._tex.save_to_filename(path)

            def save_to_filename(self, path: str) -> None:
                self._tex.save_to_filename(path)

        return _SaveAdapter(texture)

    def apply_nav_settings(self, settings: dict) -> None:
        self._nav_settings = dict(settings or {})
        view = self.view
        mapping = {
            "nav-invert-x": "invert-x",
            "nav-invert-y": "invert-y",
            "nav-zoom-to-cursor": "zoom-to-cursor",
            "nav-orbit-around-cursor": "orbit-around-cursor",
            "nav-touchpad-orbit": "touchpad-orbit",
            "nav-mmb-click-pivot": "mmb-click-pivot",
            "nav-orbit-sensitivity": "orbit-sensitivity",
            "nav-zoom-sensitivity": "zoom-sensitivity",
            "nav-pan-sensitivity": "pan-sensitivity",
        }
        for key, prop in mapping.items():
            if key not in self._nav_settings:
                continue
            try:
                view.set_property(prop, self._nav_settings[key])
            except Exception as exc:
                log.debug("apply_nav %s: %s", prop, exc)

    def _named_orbit(self, yaw: float, pitch: float) -> None:
        try:
            self.engine.reset_camera()
            if yaw or pitch:
                self.engine.rotate(float(yaw), float(pitch))
        except Exception as exc:
            log.debug("named orbit: %s", exc)

    def front_view(self, *args) -> None:
        self._named_orbit(0.0, 0.0)

    def right_view(self, *args) -> None:
        self._named_orbit(90.0, 0.0)

    def back_view(self, *args) -> None:
        self._named_orbit(180.0, 0.0)

    def left_view(self, *args) -> None:
        self._named_orbit(-90.0, 0.0)

    def top_view(self, *args) -> None:
        self._named_orbit(0.0, -80.0)

    def isometric_view(self, *args) -> None:
        self._named_orbit(35.0, -30.0)

    def get_camera_state(self) -> Any:
        eng = self.engine
        getter = getattr(eng, "get_camera_state", None)
        if not callable(getter):
            return None
        try:
            variant = getter()
        except Exception as exc:
            log.debug("get_camera_state: %s", exc)
            return None
        if variant is None:
            return None
        try:
            return tuple(variant.unpack())
        except Exception:
            return variant

    def set_camera_state(self, state) -> None:
        if state is None:
            return
        eng = self.engine
        setter = getattr(eng, "set_camera_state", None)
        if not callable(setter):
            return
        try:
            if isinstance(state, (tuple, list)) and len(state) == 9:
                from gi.repository import GLib

                setter(GLib.Variant("(ddddddddd)", tuple(float(x) for x in state)))
            else:
                setter(state)
            self.queue_render()
        except Exception as exc:
            log.debug("set_camera_state: %s", exc)

    def get_scene_parts(self) -> list[ScenePart]:
        return list(self._scene_parts)

    def get_scene_tree(self) -> list[SceneTreeNode]:
        return list(self._scene_tree)

    def get_hidden_part_indices(self) -> set[int]:
        return set(self._hidden_parts)

    def get_effective_hidden_part_indices(self) -> set[int]:
        return set(self._hidden_parts)

    def get_prepared_path(self) -> str | None:
        """Stable prepare-cache path (not hide/skin adhoc temps)."""
        base = self._base_prepared_path
        if base and os.path.isfile(base):
            return base
        path = self._prepared_path
        if path and not is_adhoc_load_temp(path) and os.path.isfile(path):
            return path
        return None

    def _base_load_path(self) -> str | None:
        """Path to filter/reload from (never a hide/skin temp)."""
        return (
            self.get_prepared_path()
            or self._loaded_filepath
        )

    def set_part_visible(self, node_index: int, visible: bool) -> bool:
        if not self._loaded_filepath:
            return False
        previous = set(self._hidden_parts)
        if visible:
            self._hidden_parts.discard(int(node_index))
        else:
            self._hidden_parts.add(int(node_index))
        if not self._reload_with_part_visibility():
            self._hidden_parts = previous
            return False
        return True

    def _reload_with_part_visibility(
        self, *, clear_animation: bool = False
    ) -> bool:
        """Filter GLB nodes then reload via Exb (fork approach, no native hide API).

        Always filter from the stable base prepared GLB — never from a previous
        ``exhibit-hide-`` temp, or unhide-all would keep meshes stripped.
        """
        filepath = self._loaded_filepath
        base = self._base_load_path()
        if not filepath or not base:
            return False
        if not str(base).lower().endswith((".glb", ".gltf")):
            return False
        cam = None
        try:
            cam = self.get_camera_state()
        except Exception:
            cam = None
        anim_time = None
        was_playing = False
        if not clear_animation:
            try:
                anim_time = float(self.animation_time)
            except Exception:
                anim_time = float(self._animation_time)
            was_playing = bool(self._playing)
            self.playing = False
        try:
            if not self._hidden_parts:
                prepared = (
                    self._base_prepared_path
                    if self._base_prepared_path
                    and not is_adhoc_load_temp(self._base_prepared_path)
                    else None
                )
                ok = self.load_file(
                    filepath,
                    prepared_path=prepared,
                    clear_animation=clear_animation,
                )
            else:
                data = build_glb_hiding_nodes_bytes(
                    filepath,
                    self._hidden_parts,
                    prepared_path=(
                        self._base_prepared_path
                        if self._base_prepared_path
                        and self._base_prepared_path != filepath
                        else None
                    ),
                )
                if not data:
                    return False
                fd, tmp = tempfile.mkstemp(prefix="exhibit-hide-", suffix=".glb")
                os.close(fd)
                with open(tmp, "wb") as handle:
                    handle.write(data)
                ok = self.load_file(
                    filepath,
                    prepared_path=tmp,
                    clear_animation=clear_animation,
                )
                if not ok:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
            if ok and cam is not None:
                try:
                    self.set_camera_state(cam)
                except Exception as exc:
                    log.debug("restore camera after hide: %s", exc)
            if ok and not clear_animation and anim_time is not None:
                try:
                    adj = self.engine.get_property("animation-adjustment")
                    if adj is not None:
                        lo = float(adj.get_lower()) / 1000.0
                        hi = float(adj.get_upper()) / 1000.0
                        t = anim_time
                        if t < lo or t > hi:
                            t = lo
                        self.animation_time = t
                    if was_playing:
                        self.playing = True
                except Exception as exc:
                    log.debug("restore animation after hide: %s", exc)
            return ok
        except Exception as exc:
            log.warning("part visibility reload failed: %s", exc)
            return False

    def _release_prepared_path(self) -> None:
        current = self._prepared_path
        base = self._base_prepared_path
        self._prepared_path = None
        self._base_prepared_path = None
        if current:
            release_load_temp(current)
        if base and base != current:
            release_prepared(base)

    def release_resources(self) -> None:
        """Drop prepare/hide temps + reset engine (tab close)."""
        self.playing = False
        self._release_prepared_path()
        self._loaded_filepath = None
        self._scene_tree = []
        self._scene_parts = []
        self._hidden_parts.clear()
        try:
            self.engine.reset()
        except Exception as exc:
            log.debug("engine.reset: %s", exc)

    def done(self) -> None:
        """Post-load idle: fit camera (legacy F3D done), never release resources."""
        if getattr(self, "_fit_camera_on_done", True):
            self.reset_to_bounds()
        self._fit_camera_on_done = True

    def supports(self, filepath: str) -> bool:
        if not filepath:
            return False
        ext = os.path.splitext(filepath)[1].lstrip(".").lower()
        try:
            allowed = [e.lower() for e in Exb.get_allowed_extensions()]
        except Exception:
            allowed = ["glb", "gltf", "obj", "stl", "fbx", "usd", "usda", "usdc"]
        return ext in allowed

    def load_file(
        self,
        filepath: str,
        prepared_path: str | None = None,
        *,
        clear_animation: bool = False,
    ) -> bool:
        """Load via Exb.Engine, with fork GLB prepare when needed."""
        if not filepath:
            return False
        load_path = prepared_path or filepath
        if prepared_path is None:
            try:
                load_path, _legacy = prepare_glb_for_load(filepath)
            except Exception as exc:
                log.warning("prepare failed: %s", exc)
                load_path = filepath
        # Drop previous on-disk load path when replaced — but never drop the
        # prepare-cache retain when switching to a hide/skin adhoc temp.
        prev = self._prepared_path
        if prev and prev != load_path:
            self._prepared_path = None
            if is_adhoc_load_temp(prev):
                release_load_temp(prev)
            elif not is_adhoc_load_temp(load_path):
                release_prepared(prev)
        try:
            # reset() restores F3D defaults — snapshot render/scene props so
            # hide/unhide and in-tab reloads do not wipe sidebar state.
            _keep = {}
            for _prop in (
                "light-intensity",
                "hdri-ambient",
                "hdri-skybox",
                "hdri-file",
                "blur-background",
                "blur-coc",
                "tone-mapping",
                "ambient-occlusion",
                "anti-aliasing",
                "blending",
                "volume-rendering",
                "volume-inverse-opacity",
                "bloom",
                "bloom-threshold",
                "bloom-intensity",
                "bloom-radius",
                "godrays",
                "godrays-intensity",
                "godrays-decay",
                "godrays-density",
                "godrays-weight",
                "ao-radius",
                "ao-bias",
                "ao-kernel-size",
                "ao-intensity",
                "show-edges",
                "edges-width",
                "point-size",
                "sprites",
                "sprites-size",
                "model-metallic",
                "model-roughness",
                "model-opacity",
                "model-color",
                "model-unlit",
                "normal-scale",
                "show-grid",
                "grid-absolute",
                "grid-color",
                "background-color",
                "up",
                "show-armature",
                "orthographic",
                "scivis",
                "scivis-array-name",
                "scivis-component",
                "scivis-cells",
                "model-checkerboard",
                "display-depth",
                "normal-glyphs",
                "normal-glyphs-scale",
            ):
                try:
                    _keep[_prop] = self.engine.get_property(_prop)
                except Exception:
                    pass
            if not clear_animation:
                try:
                    _keep["animation-index"] = self.engine.get_property(
                        "animation-index"
                    )
                except Exception:
                    pass
            self.engine.reset()
            for _prop, _val in _keep.items():
                try:
                    self.engine.set_property(_prop, _val)
                except Exception as exc:
                    log.debug("restore %s after reset: %s", _prop, exc)
            # After reset, F3D defaults indices to 0 — clear before scene.add
            # so bind pose reimport does not bake clip 0.
            if clear_animation:
                try:
                    self.engine.set_property("animation-index", -2)
                except Exception as exc:
                    log.debug("clear_animation before load: %s", exc)
            self.engine.load_file(Gio.File.new_for_path(load_path))
        except Exception as exc:
            log.warning("Exb load failed: %s", exc)
            if load_path != filepath and load_path != prev:
                release_load_temp(load_path)
            return False
        self._loaded_filepath = filepath
        if load_path == filepath:
            # Raw file — drop stale base retain if not already released as prev.
            old_base = self._base_prepared_path
            self._prepared_path = None
            self._base_prepared_path = None
            if old_base and old_base != prev:
                release_prepared(old_base)
        elif is_adhoc_load_temp(load_path):
            # Hide/skin temp: keep stable base for later unhide/filter.
            self._prepared_path = load_path
        else:
            # New prepare-cache path — release old base if it differs.
            old_base = self._base_prepared_path
            self._prepared_path = load_path
            self._base_prepared_path = load_path
            if old_base and old_base != load_path and old_base != prev:
                release_prepared(old_base)
        self._refresh_scene_graph(
            filepath if filepath.lower().endswith((".glb", ".gltf")) else load_path
        )
        self.queue_render()
        return True

    def add_file(self, filepath: str, prepared_path: str | None = None) -> bool:
        return self.load_file(filepath, prepared_path=prepared_path)

    def _refresh_scene_graph(self, path: str) -> None:
        try:
            if path and path.lower().endswith((".glb", ".gltf")):
                self._scene_tree = build_scene_tree(path) or []
                self._scene_parts = list_mesh_parts(path) or []
            else:
                self._scene_tree = []
                self._scene_parts = []
        except Exception as exc:
            log.debug("scene graph refresh failed: %s", exc)
            self._scene_tree = []
            self._scene_parts = []
