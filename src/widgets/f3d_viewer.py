# f3d_viewer.py — compatibility shim over Exb.View during libexhibit migration
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import os
from typing import Any

from gi.repository import Exb, Gio, GObject, Gtk

from ..gltf_scene_graph import ScenePart, SceneTreeNode, build_scene_tree, list_mesh_parts
from ..meshopt_decompress import prepare_glb_for_load, release_prepared

log = logging.getLogger(__name__)


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
            self.view = Exb.View()
            self.view.set_hexpand(True)
            self.view.set_vexpand(True)
            self.append(self.view)
            self.engine = self.view.get_engine()
            self._bridge = False
        self.settings: dict | None = None
        self.logger = log
        self.scene = None
        self._prepared_path: str | None = None
        self._loaded_filepath: str | None = None
        self._options_batch = 0
        self._nav_settings: dict = {}
        self._hidden_parts: set[int] = set()
        self._scene_tree: list[SceneTreeNode] = []
        self._scene_parts: list[ScenePart] = []
        self._animation_time = 0.0
        self._playing = False

    def get_view(self) -> Exb.View:
        return self.view

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
            "edge-enable": "show-edges",
            "armature-enable": "show-armature",
            "tone-mapping": "tone-mapping",
            "ambient-occlusion": "ambient-occlusion",
            "hdri-ambient": "hdri-ambient",
            "hdri-skybox": "hdri-skybox",
            "blur-background": "blur-background",
            "volume": "volume-rendering",
            "animation-index": "animation-index",
        }
        for key, value in options.items():
            prop = mapping.get(key)
            if prop is None:
                log.debug("update_options: skip unmapped %s", key)
                continue
            try:
                eng.set_property(prop, value)
            except Exception as exc:
                log.debug("update_options %s: %s", key, exc)
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
        return [str(i) for i in range(n)]

    def get_animation_keyframes(self) -> list[float]:
        return []

    @GObject.Property(type=float)
    def animation_time(self) -> float:
        return self._animation_time

    @animation_time.setter
    def animation_time(self, value: float) -> None:
        self._animation_time = float(value)

    @property
    def upper_time_range(self) -> float:
        return 1.0

    @property
    def lower_time_range(self) -> float:
        return 0.0

    @GObject.Property(type=bool, default=False)
    def playing(self) -> bool:
        return self._playing

    @playing.setter
    def playing(self, value: bool) -> None:
        self._playing = bool(value)
        if self._playing:
            try:
                self.engine.play_animation()
            except Exception as exc:
                log.debug("play_animation: %s", exc)

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

    def toggle_orthographic(self, *args) -> None:
        self.orthographic = not self.orthographic

    def reset_to_bounds(self) -> None:
        try:
            self.engine.reset_camera()
        except Exception as exc:
            log.debug("reset_camera: %s", exc)

    def reset_to_bind_pose(self) -> bool:
        try:
            self.engine.set_property("animation-index", -1)
            self.playing = False
            return True
        except Exception as exc:
            log.debug("reset_to_bind_pose: %s", exc)
            return False

    def render_image(self):
        try:
            return self.engine.render_texture()
        except Exception as exc:
            log.debug("render_texture: %s", exc)
            return None

    def apply_nav_settings(self, settings: dict) -> None:
        self._nav_settings = dict(settings or {})

    def front_view(self, *args) -> None:
        self.reset_to_bounds()

    def right_view(self, *args) -> None:
        self.reset_to_bounds()

    def back_view(self, *args) -> None:
        self.reset_to_bounds()

    def left_view(self, *args) -> None:
        self.reset_to_bounds()

    def top_view(self, *args) -> None:
        self.reset_to_bounds()

    def isometric_view(self, *args) -> None:
        self.reset_to_bounds()

    def get_camera_state(self) -> Any:
        return None

    def set_camera_state(self, state) -> None:
        return

    def get_scene_parts(self) -> list[ScenePart]:
        return list(self._scene_parts)

    def get_scene_tree(self) -> list[SceneTreeNode]:
        return list(self._scene_tree)

    def get_hidden_part_indices(self) -> set[int]:
        return set(self._hidden_parts)

    def get_effective_hidden_part_indices(self) -> set[int]:
        return set(self._hidden_parts)

    def get_prepared_path(self) -> str | None:
        return self._prepared_path

    def set_part_visible(self, node_index: int, visible: bool) -> bool:
        if visible:
            self._hidden_parts.discard(int(node_index))
        else:
            self._hidden_parts.add(int(node_index))
        log.debug("set_part_visible deferred (no Exb part API yet)")
        return False

    def _release_prepared_path(self) -> None:
        if self._prepared_path:
            release_prepared(self._prepared_path)
            self._prepared_path = None

    def release_resources(self) -> None:
        self._release_prepared_path()
        self._scene_tree = []
        self._scene_parts = []
        self._hidden_parts.clear()
        try:
            self.engine.reset()
        except Exception as exc:
            log.debug("engine.reset: %s", exc)

    def done(self) -> None:
        self.release_resources()

    def supports(self, filepath: str) -> bool:
        if not filepath:
            return False
        ext = os.path.splitext(filepath)[1].lstrip(".").lower()
        try:
            allowed = [e.lower() for e in Exb.get_allowed_extensions()]
        except Exception:
            allowed = ["glb", "gltf", "obj", "stl", "fbx", "usd", "usda", "usdc"]
        return ext in allowed

    def load_file(self, filepath: str, prepared_path: str | None = None) -> bool:
        """Load via Exb.Engine, with fork GLB prepare when needed."""
        if not filepath:
            return False
        self._release_prepared_path()
        load_path = prepared_path or filepath
        if prepared_path is None:
            try:
                load_path, _legacy = prepare_glb_for_load(filepath)
            except Exception as exc:
                log.warning("prepare failed: %s", exc)
                load_path = filepath
        try:
            self.engine.reset()
            self.engine.load_file(Gio.File.new_for_path(load_path))
        except Exception as exc:
            log.warning("Exb load failed: %s", exc)
            if load_path != filepath:
                release_prepared(load_path)
            return False
        self._loaded_filepath = filepath
        self._prepared_path = load_path if load_path != filepath else None
        self._refresh_scene_graph(filepath if filepath.lower().endswith((".glb", ".gltf")) else load_path)
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
