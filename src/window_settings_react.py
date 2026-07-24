# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings change reactions extracted from Viewer3dWindow."""

from __future__ import annotations

from .camera_views import UP_DIRS as up_dirs_vector


class SettingsReactMixin:
    """React to WindowSettings / preset action changes."""

    def update_background_color(self, *args):
        self.logger.info(
            f"Use color is: {self.window_settings.get_setting('use-color').value}")
        if self.window_settings.get_setting("use-color").value:
            options = {
                "bg-color": self.window_settings.get_setting("bg-color").value,
            }
            self._update_all_viewers_options(options)
            return
        if self.style_manager.get_dark():
            options = {"bg-color": [0.117, 0.117, 0.117]}
        else:
            options = {"bg-color": [1.0, 1.0, 1.0]}
        self._update_all_viewers_options(options)

    def on_view_setting_changed(self, window_settings, setting):
        self.logger.info(f"Setting: {setting.name} to {setting.value}")
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

        if setting.name == "up":
            self.reload_file()
        elif setting.name == "checkerboard-enable":
            # model.checkerboard.enable is applied on load.
            self.reload_file(pres_or=True)

    def on_other_setting_changed(self, window_settings, setting):
        self.logger.info(f"Setting: {setting.name} to {setting.value}")
        if setting.name == "use-color":
            self.update_background_color()
        elif setting.name == "point-up":
            for tab in self._iter_tabs():
                viewer = getattr(tab, "viewer", None)
                if viewer is None:
                    continue
                if setting.value:
                    viewer.set_view_up(
                        up_dirs_vector[
                            self.window_settings.get_setting("up").value
                        ]
                    )
                    viewer.always_point_up = True
                else:
                    viewer.always_point_up = False
        elif setting.name == "auto-reload":
            # Watcher always runs while documents are open; this flag only
            # controls silent reload of the active tab vs (modified) + prompt.
            if any(t.loaded for t in self._iter_tabs()):
                self.change_checker.run()
        elif setting.name.startswith("nav-"):
            self._apply_nav_settings_to_viewers()

        self.check_for_options_change()

    def on_internal_setting_changed(self, window_settings, setting):
        self.logger.info(f"Setting: {setting.name} to {setting.value}")
        if setting.name == "auto-best":
            pass
        elif setting.name == "sidebar-show":
            pass

    def change_setting_state(self, state):
        self.logger.debug(f"Requested changing settings to {state}")

        if state.get_string() == "custom":
            self.save_settings_action.set_enabled(True)
            self.settings_action.set_state(state)
            return

        self.set_settings_from_name(state.get_string())

        self.settings_action.set_state(state)

        self.save_settings_action.set_enabled(False)

        self.update_background_color()

    def get_gimble_limit(self):
        return self.distance / 10

