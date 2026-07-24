# SPDX-License-Identifier: GPL-3.0-or-later
"""Load / prepare / part-visibility helpers for F3DViewer."""

from __future__ import annotations

import os

import f3d

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
from ..skin_weights import cleanup_skin_weight_temp


class F3DLoadMixin:
    """Prepare/load/part-visibility methods mixed into ``F3DViewer``."""

    def _release_load_path(self, path: str | None) -> None:
        """Drop prepare-cache retain or unlink exhibit-skinw heat temps."""
        if not path or path == getattr(self, "_loaded_filepath", None):
            return
        if os.path.basename(path).startswith("exhibit-skinw-"):
            cleanup_skin_weight_temp(path)
        else:
            release_prepared(path)

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
            except Exception as exc:
                if self.logger:
                    self.logger.debug("force_reader reset failed: %s", exc)
        kept = {key: opts[key] for key in list(opts.keys()) if key != "scene.force_reader"}
        fresh = f3d.Options()
        for key, value in kept.items():
            try:
                fresh[key] = value
            except Exception as exc:
                if self.logger:
                    self.logger.debug("force_reader copy option %s failed: %s", key, exc)
        self.engine.options = fresh
        if self.settings:
            try:
                self.engine.options.update(self.settings)
            except Exception as exc:
                if self.logger:
                    self.logger.debug("force_reader restore settings failed: %s", exc)

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
        except Exception as exc:
            if self.logger:
                self.logger.debug(
                    "scene.add(bytes) needs force_reader: %s", exc
                )

        self.engine.options["scene.force_reader"] = reader
        try:
            self.scene.add(data)
        finally:
            self._clear_force_reader()

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
        self._release_load_path(previous)

    def release_resources(self) -> None:
        """Stop timers, clear scene, drop engine + prepare temps (tab close)."""
        self._playing = False
        self._stop_animation_timer()
        log = self.logger
        try:
            self.set_auto_render(False)
        except Exception as exc:
            if log:
                log.warning("release_resources: set_auto_render failed: %s", exc)

        # Make GL current so VTK/F3D can free GPU-side resources.
        try:
            if self.get_realized():
                self.make_current()
        except Exception as exc:
            if log:
                log.warning("release_resources: make_current failed: %s", exc)

        if self.scene is not None:
            try:
                self.scene.clear()
            except Exception as exc:
                if log:
                    log.warning("release_resources: scene.clear failed: %s", exc)

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
            self._release_load_path(prepared_path)

        previous_prepared = self._prepared_path
        self.scene.clear()
        self._hidden_part_indices = set()

        load_path, meshopt_temp = self._resolve_load_path(filepath, prepared_path)
        if load_path is None:
            self._loaded_filepath = None
            self._prepared_path = None
            self._release_load_path(previous_prepared)
            return False

        try:
            self.scene.add(load_path)
        except Exception as e:
            self.logger.error(f"Error while loading file: {e}")
            self._loaded_filepath = None
            self._prepared_path = None
            if previous_prepared and previous_prepared != load_path:
                self._release_load_path(previous_prepared)
            if load_path != filepath and load_path != previous_prepared:
                self._release_load_path(load_path)
            return False
        finally:
            cleanup_decompressed(meshopt_temp)

        self._loaded_filepath = filepath
        self._prepared_path = load_path
        if previous_prepared and previous_prepared != load_path:
            self._release_load_path(previous_prepared)
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
                self._release_load_path(load_path)
            return False
        finally:
            cleanup_decompressed(meshopt_temp)

        previous_prepared = self._prepared_path
        self._loaded_filepath = filepath
        self._prepared_path = load_path
        if previous_prepared and previous_prepared != load_path:
            self._release_load_path(previous_prepared)
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

    def reset_to_bind_pose(self) -> bool:
        """
        Reimport with empty ``scene.animation.indices``.

        Clearing indices alone leaves the last skin pose; F3D only restores
        bind/rest pose when the file is loaded with no clip enabled.
        """
        return self._reload_with_part_visibility(restore_animation_time=False)

    def _try_native_part_visibility(self) -> bool:
        """
        Apply node hide via F3D Scene when the build exposes an API.

        Returns True if visibility was applied without rewriting the GLB.
        Most Flatpak/libf3d builds lack this; callers fall back to filter+reload.
        """
        scene = self.scene
        if scene is None:
            return False
        hidden = self.get_effective_hidden_part_indices()
        for attr in ("set_node_visibilities", "set_actors_visibility"):
            fn = getattr(scene, attr, None)
            if not callable(fn):
                continue
            try:
                fn(hidden)
                self.queue_render()
                return True
            except TypeError:
                try:
                    parts = self.get_scene_parts()
                    mapping = {
                        part.node_index: part.node_index not in hidden
                        for part in parts
                    }
                    fn(mapping)
                    self.queue_render()
                    return True
                except Exception as exc:
                    if self.logger:
                        self.logger.debug("native %s failed: %s", attr, exc)
            except Exception as exc:
                if self.logger:
                    self.logger.debug("native %s failed: %s", attr, exc)

        setter = getattr(scene, "set_actor_visible", None) or getattr(
            scene, "set_node_visible", None
        )
        if not callable(setter):
            return False
        try:
            for part in self.get_scene_parts():
                setter(part.node_index, part.node_index not in hidden)
            self.queue_render()
            return True
        except Exception as exc:
            if self.logger:
                self.logger.debug("native per-node visibility failed: %s", exc)
            return False

    def _reload_with_part_visibility(self, *, restore_animation_time: bool = True) -> bool:
        """
        Reimport scene with hidden meshes stripped from GLB JSON.

        Prefer native Scene visibility when available; otherwise clear+add with
        an in-memory filtered GLB (avoids temp files).
        """
        filepath = self._loaded_filepath
        prepared = self._prepared_path
        if not filepath:
            return False

        if self._try_native_part_visibility():
            return True

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

        # Options (incl. empty animation indices) must be current before add.
        if self.engine and self.settings:
            try:
                self.engine.options.update(self.settings)
            except Exception as exc:
                if self.logger:
                    self.logger.warning(
                        "part visibility: options.update failed: %s", exc
                    )

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
                except Exception as restore_exc:
                    if self.logger:
                        self.logger.warning(
                            "part visibility: restore scene failed: %s",
                            restore_exc,
                        )
                raise
        except Exception as e:
            self.logger.error(f"Error while updating part visibility: {e}")
            return False

        self.notify("lower-time-range")
        self.notify("upper-time-range")

        if restore_animation_time:
            lower = self.lower_time_range
            upper = self.upper_time_range
            if anim_time < lower or anim_time > upper:
                anim_time = lower
            self.animation_time = anim_time

        if camera_state is not None:
            try:
                self.set_camera_state(camera_state)
            except Exception as exc:
                if self.logger:
                    self.logger.warning(
                        "part visibility: restore camera failed: %s", exc
                    )

        if was_playing and restore_animation_time:
            self.playing = True

        self.queue_render()
        return True

