# SPDX-License-Identifier: GPL-3.0-or-later
"""Window lifecycle helpers extracted from Viewer3dWindow."""

from __future__ import annotations

from gi.repository import Gtk

from .meshopt_decompress import clear_prepare_cache


class LifecycleMixin:
    """Close / home / session-preference callbacks."""

    def _init_home_button(self) -> None:
        # Header chrome under the viewer paned: template callbacks often do not
        # fire; connect in code like preferences / theme.
        btn = getattr(self, "home_button_headerbar", None)
        if btn is not None:
            btn.connect("clicked", self.on_home_clicked)

    def on_home_clicked(self, *args):
        viewer = getattr(self, "f3d_viewer", None)
        if viewer is None:
            return
        reset = getattr(viewer, "reset_to_bounds", None)
        if callable(reset):
            reset()

    def on_restore_session_toggled(self, switch, *_args):
        if not switch.get_active():
            self.saved_settings.set_strv("session-files", [])

    @Gtk.Template.Callback("on_close_request")
    def on_close_request(self, window):
        self.logger.debug("window closed, saving settings")
        self.change_checker.stop()
        teardown = getattr(self, "_teardown_split_compare_viewer", None)
        if callable(teardown):
            try:
                teardown()
            except Exception as exc:
                self.logger.warning("close: split compare teardown failed: %s", exc)
        for tab in list(self._iter_tabs()):
            self._cancel_warm_load(tab)
            try:
                tab.viewer.release_resources()
            except Exception as exc:
                self.logger.warning(
                    "close: release_resources failed: %s", exc
                )
        # Global prepare cache is shared across windows — only flush when
        # this is the last Viewer3dWindow still alive.
        app = self.get_application()
        sibling_windows = 0
        if app is not None:
            sibling_windows = sum(
                1 for w in app.get_windows()
                if w is not self and isinstance(w, type(self))
            )
        if sibling_windows == 0:
            clear_prepare_cache()
        self.saved_settings.set_int(
            "startup-width", window.get_width())
        self.saved_settings.set_int(
            "startup-height", window.get_height())
        self.saved_settings.set_boolean(
            "startup-sidebar-show", window.split_view.get_show_sidebar())
        self.saved_settings.set_boolean(
            "auto-best", self.window_settings.get_setting("auto-best").value)
        try:
            self.saved_settings.set_boolean(
                "split-compare-enabled",
                bool(getattr(self, "_split_compare", False)),
            )
        except Exception:
            pass
        if hasattr(self, "_persist_nav_settings_to_gschema"):
            self._persist_nav_settings_to_gschema()
        self._persist_session_files()

