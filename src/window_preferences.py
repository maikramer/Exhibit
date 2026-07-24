# SPDX-License-Identifier: GPL-3.0-or-later
"""Preferences dialog + theme header menu."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Gio, GLib

from .camera_nav import NAV_SETTING_DEFAULTS

_THEME_ICONS = {
    "follow": "preferences-desktop-appearance-symbolic",
    "light": "display-brightness-symbolic",
    "dark": "weather-clear-night-symbolic",
}
_THEME_LABELS = {
    "follow": "Follow System",
    "light": "Light",
    "dark": "Dark",
}
_THEME_TOOLTIPS = {
    "follow": "Theme: Follow System",
    "light": "Theme: Light",
    "dark": "Theme: Dark",
}
_THEME_ORDER = ("follow", "light", "dark")

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
        self.create_action("preferences", self.on_preferences_clicked)
        self._setup_theme_menu()
        app = self.get_application()
        if app is not None:
            app.set_accels_for_action("win.preferences", ["<Primary>comma"])
        self._sync_theme_toggle_button()

    def on_preferences_clicked(self, *args):
        dialog = getattr(self, "preferences_dialog", None)
        if dialog is None:
            return
        dialog.present(self)

    def _setup_theme_menu(self) -> None:
        btn = getattr(self, "theme_toggle_button", None)
        if btn is None:
            return
        section = Gio.Menu()
        for key in _THEME_ORDER:
            item = Gio.MenuItem.new(_(_THEME_LABELS[key]), None)
            item.set_action_and_target_value(
                "app.theme", GLib.Variant("s", key)
            )
            item.set_icon(Gio.ThemedIcon.new(_THEME_ICONS[key]))
            section.append_item(item)
        menu = Gio.Menu()
        menu.append_section(None, section)
        btn.set_menu_model(menu)

    def _sync_theme_toggle_button(self) -> None:
        btn = getattr(self, "theme_toggle_button", None)
        if btn is None:
            return
        app = self.get_application()
        theme = "follow"
        if app is not None:
            theme = app.saved_settings.get_string("theme")
        if theme not in _THEME_ICONS:
            theme = "follow"
        btn.set_icon_name(_THEME_ICONS[theme])
        btn.set_tooltip_text(_(_THEME_TOOLTIPS[theme]))

    def _load_nav_settings_from_gschema(self) -> None:
        settings = self.saved_settings
        for key in _NAV_BOOL_KEYS:
            try:
                self.window_settings.set_setting(
                    key, settings.get_boolean(key), False
                )
            except Exception:
                self.window_settings.set_setting(
                    key, NAV_SETTING_DEFAULTS[key], False
                )
        for key in _NAV_FLOAT_KEYS:
            try:
                self.window_settings.set_setting(
                    key, float(settings.get_double(key)), False
                )
            except Exception:
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
            except Exception:
                pass
        for key in _NAV_FLOAT_KEYS:
            try:
                settings.set_double(
                    key, float(self.window_settings.get_setting(key).value)
                )
            except Exception:
                pass

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
