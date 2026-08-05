# SPDX-License-Identifier: GPL-3.0-or-later
"""Preferences dialog + theme header menu."""

from __future__ import annotations

from .camera_nav import NAV_SETTING_DEFAULTS

_NAV_BOOL_KEYS = (
    "nav-invert-x",
    "nav-invert-y",
    "nav-zoom-to-cursor",
    "nav-orbit-around-cursor",
    "nav-touchpad-orbit",
    "nav-mmb-click-pivot",
)
_NAV_FLOAT_KEYS = (
    "nav-orbit-sensitivity",
    "nav-zoom-sensitivity",
    "nav-pan-sensitivity",
)


class PreferencesMixin:
    """Open Preferences dialog and theme menu from the header bar."""

    def _init_preferences_actions(self) -> None:
        # Wire with plain methods: Gtk template callbacks are CallThing wrappers
        # and break Gio.SimpleAction / Python invoke.
        # Menu uses win.preferences; app.open-preferences owns the accel
        # (see shortcuts-dialog.ui / ExhibitApplication).
        self.create_action("preferences", self.on_preferences_clicked)

    def on_preferences_clicked(self, *args):
        """Open sidebar More (nav / session / loading) — not Save Settings."""
        split = getattr(self, "split_view", None)
        if split is not None:
            split.set_show_sidebar(True)
        stack = getattr(self, "sidebar_stack", None)
        if stack is not None:
            try:
                stack.set_visible_child_name("more")
            except Exception as exc:
                log = getattr(self, "logger", None)
                if log:
                    log.debug("preferences sidebar more: %s", exc)
        # Persist so next launch keeps prefs reachable.
        try:
            self.window_settings.set_setting("sidebar-show", True, False)
        except Exception:
            pass

    def _sync_theme_toggle_button(self) -> None:
        # Upstream theme lives in primary_menu ThemeSwitcher; no header toggle.
        return

    def _load_nav_settings_from_gschema(self) -> None:
        settings = self.saved_settings
        for key in _NAV_BOOL_KEYS:
            try:
                self.window_settings.set_setting(
                    key, settings.get_boolean(key), False
                )
            except Exception as exc:
                self.logger.debug("nav gschema bool %s: %s", key, exc)
                self.window_settings.set_setting(
                    key, NAV_SETTING_DEFAULTS[key], False
                )
        for key in _NAV_FLOAT_KEYS:
            try:
                self.window_settings.set_setting(
                    key, float(settings.get_double(key)), False
                )
            except Exception as exc:
                self.logger.debug("nav gschema float %s: %s", key, exc)
                self.window_settings.set_setting(
                    key, NAV_SETTING_DEFAULTS[key], False
                )
        self._apply_nav_settings_to_viewers()

    def _persist_nav_settings_to_gschema(self) -> None:
        settings = self.saved_settings
        for key in _NAV_BOOL_KEYS:
            try:
                settings.set_boolean(
                    key, bool(self.window_settings.get_setting(key).value)
                )
            except Exception as exc:
                self.logger.debug("nav gschema persist bool %s: %s", key, exc)
        for key in _NAV_FLOAT_KEYS:
            try:
                settings.set_double(
                    key, float(self.window_settings.get_setting(key).value)
                )
            except Exception as exc:
                self.logger.debug("nav gschema persist float %s: %s", key, exc)

    def _nav_settings_dict(self) -> dict:
        out = {}
        for key in (*_NAV_BOOL_KEYS, *_NAV_FLOAT_KEYS):
            try:
                out[key] = self.window_settings.get_setting(key).value
            except Exception:
                out[key] = NAV_SETTING_DEFAULTS[key]
        return out

    def _apply_nav_settings_to_viewers(self) -> None:
        opts = self._nav_settings_dict()
        for tab in self._iter_tabs():
            viewer = getattr(tab, "viewer", None)
            if viewer is not None and hasattr(viewer, "apply_nav_settings"):
                viewer.apply_nav_settings(opts)
        split = getattr(self, "_split_compare_viewer", None)
        if split is not None and hasattr(split, "apply_nav_settings"):
            split.apply_nav_settings(opts)
