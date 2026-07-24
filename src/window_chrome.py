# SPDX-License-Identifier: GPL-3.0-or-later
"""Play / orthographic / external-open chrome extracted from Viewer3dWindow."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Gio, GLib, Gtk


class ChromeMixin:
    """Viewport chrome actions (play, ortho, open externally)."""

    def orthographic_state_changed(self, action, state):
        action.set_state(state)
        self.window_settings.set_setting("orthographic", state.get_boolean())
        self._update_all_viewers_options(
            {"orthographic": state.get_boolean()})

    def on_orthographic_changed(self, setting, *args):
        self.orthographic_action.set_state(
            GLib.Variant(
                "b", self.window_settings.get_setting("orthographic").value))

    def toggle_orthographic(self, *args):
        self.window_settings.set_setting(
            "orthographic",
            not self.window_settings.get_setting("orthographic").value)

    def open_with_external_app(self):
        try:
            file = Gio.File.new_for_path(self.filepath)
        except Exception:
            self.logger.error("Failed to construct a new Gio.File from path.")
        else:
            launcher = Gtk.FileLauncher.new(file)
            launcher.set_always_ask(True)
            launcher.launch(self, None, None)

    def on_play_button_clicked(self, btn):
        if self.window_settings.get_setting("animation-index").value is None:
            return
        self.f3d_viewer.playing = not self.f3d_viewer.playing

    def on_playing_changed(self, *args):
        if self.f3d_viewer.playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
            self.play_button.set_tooltip_text(_("Stop"))
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")
            self.play_button.set_tooltip_text(_("Start"))

