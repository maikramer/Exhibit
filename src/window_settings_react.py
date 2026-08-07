# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings change reactions extracted from Viewer3dWindow."""

from __future__ import annotations

from gi.repository import GLib

from .camera_views import UP_DIRS as up_dirs_vector


class SettingsReactMixin:
    """React to WindowSettings / preset action changes."""

    def _apply_point_up_to_viewer(self, viewer) -> None:
        """Seed ``always_point_up`` / view-up from the current setting."""
        if viewer is None:
            return
        enabled = bool(self.window_settings.get_setting("point-up").value)
        if enabled:
            up_key = self.window_settings.get_setting("up").value
            up_vec = up_dirs_vector.get(up_key) or up_dirs_vector["+Y"]
            viewer.set_view_up(up_vec)
            viewer.always_point_up = True
        else:
            viewer.always_point_up = False

    def _apply_point_up_to_viewers(self) -> None:
        for tab in self._iter_tabs():
            self._apply_point_up_to_viewer(getattr(tab, "viewer", None))
        self._apply_point_up_to_viewer(
            getattr(self, "_split_compare_viewer", None)
        )

    # update_background_color / change_setting_state live on ExbWindow
    # (engine-direct + preset apply). Do not duplicate here.

    def on_view_setting_changed(self, window_settings, setting):
        self.logger.debug("Setting: %s to %s", setting.name, setting.value)
        if setting.name == "armature-enable":
            self._apply_armature_mode(bool(setting.value))
            self.check_for_options_change()
            return
        if setting.name == "display-depth":
            self._apply_display_depth_mode(bool(setting.value))
            self.check_for_options_change()
            return
        if setting.name == "normal-glyphs":
            self._apply_normal_glyphs_mode(bool(setting.value))
            self.check_for_options_change()
            return
        if setting.name == "skin-weights":
            self._apply_skin_weights_mode(bool(setting.value))
            self.check_for_options_change()
            return
        if setting.name in ("skin-weights-mode", "skin-weights-joint"):
            if self.window_settings.get_setting("skin-weights").value:
                self._apply_skin_weights_mode(True)
            self.check_for_options_change()
            return
        if setting.name == "stats-overlay":
            self._apply_stats_overlay(bool(setting.value))
            self.check_for_options_change()
            return

        options = {setting.name: setting.value}
        self._update_all_viewers_options(options)
        self.check_for_options_change()

        if setting.name in ("up", "checkerboard-enable"):
            # Applied at load — reload every loaded tab (not only active).
            pres_or = setting.name == "checkerboard-enable"
            for tab in self._iter_tabs():
                if not getattr(tab, "loaded", False) or not tab.filepath:
                    continue
                self._reload_tab(tab, preserve_orientation=pres_or)
            if getattr(self, "_split_compare", False):
                GLib.idle_add(self._load_split_compare_from_active)

    def on_other_setting_changed(self, window_settings, setting):
        self.logger.debug("Setting: %s to %s", setting.name, setting.value)
        if setting.name == "use-color":
            self.update_background_color()
        elif setting.name == "point-up":
            self._apply_point_up_to_viewers()
        elif setting.name == "auto-reload":
            # Watcher always runs while documents are open; this flag only
            # controls silent reload of the active tab vs (modified) + prompt.
            if any(t.loaded for t in self._iter_tabs()):
                self.change_checker.run()
        elif setting.name == "nav-show-cube":
            apply_cube = getattr(self, "_apply_nav_cube_visibility", None)
            if callable(apply_cube):
                apply_cube()
        elif setting.name.startswith("nav-"):
            self._apply_nav_settings_to_viewers()

        self.check_for_options_change()

    def on_internal_setting_changed(self, window_settings, setting):
        self.logger.debug("Setting: %s to %s", setting.name, setting.value)
        if setting.name == "auto-best":
            pass
        elif setting.name == "sidebar-show":
            pass

    def get_gimble_limit(self):
        return self.distance / 10

