# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh stats / armature inspect overlays extracted from Viewer3dWindow."""

from __future__ import annotations

import os

from gettext import gettext as _

from .gltf_scene_graph import glb_has_skins, gltf_needs_skin_skeleton_fix
from .mesh_stats import collect_mesh_stats, format_overlay_text
from .meshopt_decompress import _read_glb_json
from .skin_weights import (
    HEAT_ATTR,
    WEIGHTS_ARRAY,
    cleanup_skin_weight_temp,
    gltf_has_skin_weights,
    list_skin_joints,
    mode_to_component,
    write_skin_weight_heat_temp,
)


class InspectMixin:
    """Stats HUD and armature X-ray presentation."""

    def _refresh_mesh_stats(self) -> None:
        tab = self._active_tab()
        if tab is None:
            self._mesh_stats = None
            return
        path = tab.viewer.get_prepared_path() or tab.filepath
        if not path or not os.path.isfile(path):
            self._mesh_stats = None
            tab.mesh_stats = None
            return
        up = self.window_settings.get_setting("up").value
        try:
            # Path comes from the viewer post-load — do not re-prepare.
            stats = collect_mesh_stats(path, already_prepared=True, up=up)
        except Exception as exc:
            self.logger.error(f"Failed to collect mesh stats: {exc}")
            stats = None
        self._mesh_stats = stats
        tab.mesh_stats = stats

    def _apply_stats_overlay(self, enabled: bool) -> None:
        """Show/hide the Gtk stats overlay; refresh counts when enabling."""
        if enabled:
            if self._mesh_stats is None:
                self._refresh_mesh_stats()
            if self._mesh_stats is not None:
                self.stats_overlay_label.set_label(
                    format_overlay_text(self._mesh_stats)
                )
            else:
                self.stats_overlay_label.set_label(_("No stats available"))
            self.stats_overlay_label.set_visible(True)
            # Also drive F3D's native metadata + our text via filename_info.
            info = (
                format_overlay_text(self._mesh_stats)
                if self._mesh_stats is not None
                else ""
            )
            if self.f3d_viewer.engine:
                self.f3d_viewer.engine.options.update(
                    {
                        "ui.metadata": True,
                        "ui.filename": True,
                        "ui.filename_info": info,
                        "ui.backdrop.opacity": 0.55,
                    }
                )
                self.f3d_viewer.queue_render()
            return

        self.stats_overlay_label.set_visible(False)
        if self.f3d_viewer.engine:
            self.f3d_viewer.engine.options.update(
                {
                    "ui.metadata": False,
                    "ui.filename": False,
                    "ui.filename_info": "",
                }
            )
            self.f3d_viewer.queue_render()

    def _prepared_needs_skeleton_fix(self) -> bool:
        path = self.f3d_viewer.get_prepared_path() or self.filepath
        if not path or not os.path.isfile(path):
            return False
        try:
            return gltf_needs_skin_skeleton_fix(_read_glb_json(path))
        except Exception:
            return False

    def _apply_armature_mode(self, enabled: bool):
        """
        Toggle F3D armature and apply an X-ray presentation.

        F3D/VTK only builds armature actors when ``skin.skeleton`` is set.
        Prepare fills that field; if the open temp still lacks it, reload.
        """
        xray_opacity = 0.35
        min_line_width = 4.0
        joint_point_size = 8.0

        tab = self._active_tab()
        if enabled:
            if self.window_settings.get_setting("display-depth").value:
                self.window_settings.set_setting("display-depth", False)

            if self._armature_xray_restore is None:
                self._armature_xray_restore = {
                    "model-opacity": float(
                        self.window_settings.get_setting("model-opacity").value
                    ),
                    "edges-width": float(
                        self.window_settings.get_setting("edges-width").value
                    ),
                    "point-size": float(
                        self.window_settings.get_setting("point-size").value
                    ),
                }
            if tab is not None:
                tab.armature_xray_restore = self._armature_xray_restore
            line_width = max(
                min_line_width, float(self._armature_xray_restore["edges-width"])
            )
            self.window_settings.begin_view_batch()
            try:
                self.window_settings.set_setting("model-opacity", xray_opacity)
                self.window_settings.set_setting("edges-width", line_width)
                self.window_settings.set_setting("point-size", joint_point_size)
            finally:
                self.window_settings.end_view_batch()

            armature_opts = {
                "armature-enable": True,
                "model-opacity": xray_opacity,
                "edges-width": line_width,
                "point-size": joint_point_size,
                # Depth peeling so translucent mesh + bones composite correctly.
                "translucency-support": True,
            }
            self.f3d_viewer.update_options(armature_opts)
            split = getattr(self, "_split_compare_viewer", None)
            if split is not None:
                try:
                    split.update_options(armature_opts)
                except Exception:
                    pass

            probe = self.f3d_viewer.get_prepared_path() or self.filepath
            has_skins = glb_has_skins(probe) if probe else None
            if has_skins is False:
                self.send_toast(_("No armature found in this model"))
                return

            # Actors are created at load; missing skin.skeleton → empty overlay.
            if self._prepared_needs_skeleton_fix():
                self.send_toast(_("Rebuilding armature…"), timeout=2)
                self.reload_file(pres_or=True)
            return

        restore = self._armature_xray_restore or {
            "model-opacity": 1.0,
            "edges-width": 1.0,
            "point-size": 1.0,
        }
        self._armature_xray_restore = None
        if tab is not None:
            tab.armature_xray_restore = None
        self.window_settings.begin_view_batch()
        try:
            self.window_settings.set_setting(
                "model-opacity", restore["model-opacity"]
            )
            self.window_settings.set_setting("edges-width", restore["edges-width"])
            self.window_settings.set_setting(
                "point-size", restore.get("point-size", 1.0)
            )
        finally:
            self.window_settings.end_view_batch()

        armature_opts = {
            "armature-enable": False,
            "model-opacity": restore["model-opacity"],
            "edges-width": restore["edges-width"],
            "point-size": restore.get("point-size", 1.0),
        }
        self.f3d_viewer.update_options(armature_opts)
        split = getattr(self, "_split_compare_viewer", None)
        if split is not None:
            try:
                split.update_options(armature_opts)
            except Exception:
                pass

    def _apply_display_depth_mode(self, enabled: bool) -> None:
        """
        Toggle depth buffer viz.

        F3D ignores translucent/volumetric geometry in the depth pass, so a
        mesh left at X-ray opacity yields a blank/white frame. Force opaque
        and enable scalar colormap for a readable depth image.
        """
        tab = self._active_tab()
        if enabled:
            if self.window_settings.get_setting("normal-glyphs").value:
                self.window_settings.set_setting("normal-glyphs", False)
            if self.window_settings.get_setting("skin-weights").value:
                self.window_settings.set_setting("skin-weights", False)

            if getattr(self, "_depth_opacity_restore", None) is None:
                self._depth_opacity_restore = float(
                    self.window_settings.get_setting("model-opacity").value
                )
            if tab is not None:
                tab.depth_opacity_restore = self._depth_opacity_restore

            self.window_settings.begin_view_batch()
            try:
                self.window_settings.set_setting("model-opacity", 1.0)
                # Keep armature actors if on, but mesh must be opaque for depth.
            finally:
                self.window_settings.end_view_batch()

            opts = {
                "display-depth": True,
                "model-opacity": 1.0,
                # Colormap path (see F3D display_depth docs).
                "scivis-enabled": True,
            }
            self._update_all_viewers_options(opts)
            # Clipping / first paint often need a kick after pass swap.
            try:
                self.f3d_viewer.queue_render()
            except Exception:
                pass
            return

        restore = getattr(self, "_depth_opacity_restore", None)
        self._depth_opacity_restore = None
        if tab is not None:
            tab.depth_opacity_restore = None
        opacity = (
            float(restore)
            if restore is not None
            else float(self.window_settings.get_setting("model-opacity").value)
        )
        # If armature x-ray is still on, prefer its opacity.
        if self.window_settings.get_setting("armature-enable").value:
            opacity = 0.35
        self.window_settings.begin_view_batch()
        try:
            self.window_settings.set_setting("model-opacity", opacity)
        finally:
            self.window_settings.end_view_batch()
        self._update_all_viewers_options(
            {
                "display-depth": False,
                "scivis-enabled": False,
                "model-opacity": opacity,
            }
        )

    def _apply_normal_glyphs_mode(self, enabled: bool) -> None:
        """Toggle normal glyphs; depth pass hides overlays so disable it."""
        if enabled and self.window_settings.get_setting("display-depth").value:
            self.window_settings.set_setting("display-depth", False)
        scale = float(
            self.window_settings.get_setting("normal-glyphs-scale").value or 1.0
        )
        scale = max(0.05, min(scale, 10.0))
        self._update_all_viewers_options(
            {
                "normal-glyphs": bool(enabled),
                "normal-glyphs-scale": scale,
            }
        )
        # Glyph actors configure on the next prepare/render.
        try:
            self.f3d_viewer.queue_render()
        except Exception:
            pass

    def _cleanup_skin_weight_heat(self) -> None:
        heat = getattr(self, "_skin_weights_heat_temp", None)
        self._skin_weights_heat_temp = None
        cleanup_skin_weight_temp(heat)

    def _reload_skin_weights_base(self, base: str | None) -> None:
        """Reload base prepared GLB after a bone-heat temp (before unlinking it)."""
        tab = self._active_tab()
        if (
            not base
            or not tab
            or not tab.filepath
            or not os.path.isfile(base)
            or self.f3d_viewer.get_prepared_path() == base
        ):
            return
        cam = None
        try:
            cam = self.f3d_viewer.get_camera_state()
        except Exception:
            pass
        self.f3d_viewer.load_file(tab.filepath, prepared_path=base)
        if cam is not None:
            try:
                self.f3d_viewer.set_camera_state(cam)
            except Exception:
                pass

    def _skin_weights_source_path(self) -> str | None:
        """Base prepared GLB (not an exhibit-skinw heat temp)."""
        base = getattr(self, "_skin_weights_base_path", None)
        if base and os.path.isfile(base):
            return base
        path = self.f3d_viewer.get_prepared_path() or self.filepath
        if path and os.path.basename(path).startswith("exhibit-skinw-"):
            return self.filepath if self.filepath else None
        return path if path and os.path.isfile(path) else None

    def _refresh_skin_weights_joint_combo(self) -> None:
        """Fill joint combo from the active document's first skin."""
        combo = getattr(self, "skin_weights_joint_combo", None)
        if combo is None:
            return
        from gi.repository import Gtk

        path = self._skin_weights_source_path()
        joints: list = []
        if path:
            try:
                gltf = _read_glb_json(path)
                if gltf_has_skin_weights(gltf):
                    joints = list_skin_joints(gltf)
            except Exception as exc:
                self.logger.debug("skin weights joints: %s", exc)
        names = [j.name for j in joints] or [_("No joints")]
        model = Gtk.StringList.new(names)
        combo.set_model(model)
        self._skin_weights_joints = joints
        current = int(self.window_settings.get_setting("skin-weights-joint").value)
        if joints:
            combo.set_selected(max(0, min(current, len(joints) - 1)))
        else:
            combo.set_selected(0)
        mode = str(self.window_settings.get_setting("skin-weights-mode").value)
        combo.set_sensitive(
            bool(joints)
            and bool(self.window_settings.get_setting("skin-weights").value)
            and mode == "bone"
        )

    def _apply_skin_weights_options(self) -> None:
        """Push scivis options for the current skin-weights mode."""
        mode = str(self.window_settings.get_setting("skin-weights-mode").value)
        component = mode_to_component(mode)
        if component is None:
            array_name = HEAT_ATTR
            component = 0
        else:
            array_name = WEIGHTS_ARRAY
        opts = {
            "scivis-enabled": True,
            "cells": False,
            "scivis-component": component,
            "scalar": array_name,
            "scalar-bar": True,
            "model-opacity": 1.0,
        }
        self._update_all_viewers_options(opts)
        # Clear base-color texture influence for a clean heat map when possible.
        if self.f3d_viewer.engine:
            try:
                self.f3d_viewer.engine.options.update({"model.unlit": True})
            except Exception:
                pass
            self.f3d_viewer.queue_render()

    def _apply_skin_weights_mode(self, enabled: bool) -> None:
        """Toggle WEIGHTS_0 / joint-heat scivis overlay."""
        tab = self._active_tab()
        if not enabled:
            base = getattr(self, "_skin_weights_base_path", None)
            had_heat = bool(getattr(self, "_skin_weights_heat_temp", None))
            self._skin_weights_base_path = None
            # Reload base while heat temp still on disk; load_file unlinks it.
            if had_heat:
                self._reload_skin_weights_base(base)
                self._skin_weights_heat_temp = None
            else:
                self._cleanup_skin_weight_heat()
            restore = getattr(self, "_skin_weights_scivis_restore", None) or {
                "scivis-enabled": False,
                "cells": True,
                "scivis-component": -1,
                "scalar-bar": False,
            }
            self._skin_weights_scivis_restore = None
            # Drop empty scalar — optional F3D option rejects "".
            restore.pop("scalar", None)
            self._update_all_viewers_options(restore)
            if self.f3d_viewer.engine:
                try:
                    self.f3d_viewer.engine.options.update({"model.unlit": False})
                except Exception:
                    pass
            self._refresh_skin_weights_joint_combo()
            return

        if self.window_settings.get_setting("display-depth").value:
            self.window_settings.set_setting("display-depth", False)

        path = self._skin_weights_source_path()
        if not path:
            self.send_toast(_("No model loaded"))
            self.window_settings.set_setting("skin-weights", False)
            return
        try:
            gltf = _read_glb_json(path)
        except Exception as exc:
            self.logger.error("skin weights: %s", exc)
            self.window_settings.set_setting("skin-weights", False)
            return
        if not gltf_has_skin_weights(gltf):
            self.send_toast(_("No skin weights in this model"))
            self.window_settings.set_setting("skin-weights", False)
            return

        if getattr(self, "_skin_weights_scivis_restore", None) is None:
            self._skin_weights_scivis_restore = {
                "scivis-enabled": bool(
                    self.window_settings.get_setting("scivis-enabled").value
                ),
                "cells": bool(self.window_settings.get_setting("cells").value),
                "scivis-component": int(
                    self.window_settings.get_setting("scivis-component").value
                ),
                "scalar": str(
                    self.window_settings.get_setting("scalar").value or ""
                ),
                "scalar-bar": False,
            }

        mode = str(self.window_settings.get_setting("skin-weights-mode").value)
        if mode == "bone":
            self._skin_weights_base_path = path
            joint_i = int(
                self.window_settings.get_setting("skin-weights-joint").value
            )
            joints = list_skin_joints(gltf)
            if not joints:
                self.send_toast(_("No joints in this model"))
                self.window_settings.set_setting("skin-weights", False)
                return
            joint_i = max(0, min(joint_i, len(joints) - 1))
            try:
                heat = write_skin_weight_heat_temp(path, joint_i)
            except Exception as exc:
                self.logger.error("skin weight heat failed: %s", exc)
                self.send_toast(_("Can't build skin weight view: {}").format(exc))
                self.window_settings.set_setting("skin-weights", False)
                return
            # load_file releases the previous prepared path (old heat / meshopt).
            self._skin_weights_heat_temp = heat
            cam = None
            try:
                cam = self.f3d_viewer.get_camera_state()
            except Exception:
                pass
            ok = self.f3d_viewer.load_file(
                tab.filepath if tab else path, prepared_path=heat
            )
            if not ok:
                cleanup_skin_weight_temp(heat)
                self._skin_weights_heat_temp = None
                self.send_toast(_("Can't load skin weight view"))
                self.window_settings.set_setting("skin-weights", False)
                return
            if cam is not None:
                try:
                    self.f3d_viewer.set_camera_state(cam)
                except Exception:
                    pass
        else:
            # Leaving bone heat → native WEIGHTS_0: restore base geometry first.
            base = getattr(self, "_skin_weights_base_path", None) or path
            if getattr(self, "_skin_weights_heat_temp", None):
                self._reload_skin_weights_base(base)
                # load_file already unlinked the heat temp.
                self._skin_weights_heat_temp = None
            else:
                self._cleanup_skin_weight_heat()

        self._apply_skin_weights_options()
        self._refresh_skin_weights_joint_combo()
