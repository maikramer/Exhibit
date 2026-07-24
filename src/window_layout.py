# SPDX-License-Identifier: GPL-3.0-or-later
"""Split-view / breakpoint layout helpers extracted from Viewer3dWindow."""

from __future__ import annotations

from gi.repository import Gtk


class LayoutMixin:
    """Sidebar collapse / narrow breakpoint callbacks."""

    @Gtk.Template.Callback("on_close_sidebar_clicked")
    def on_close_sidebar_clicked(self, *args):
        self.split_view.set_show_sidebar(False)

    @Gtk.Template.Callback("on_apply_breakpoint")
    def on_apply_breakpoint(self, *args):
        self.applying_breakpoint = True
        self.split_view.set_collapsed(True)
        self.split_view.set_show_sidebar(False)
        self.applying_breakpoint = False

    @Gtk.Template.Callback("on_unapply_breakpoint")
    def on_unapply_breakpoint(self, *args):
        state = self.window_settings.get_setting("sidebar-show").value
        self.applying_breakpoint = True
        self.split_view.set_collapsed(False)
        self.split_view.set_show_sidebar(state)
        self.applying_breakpoint = False

    @Gtk.Template.Callback("on_split_view_show_sidebar_changed")
    def on_split_view_show_sidebar_changed(self, *args):
        if self.applying_breakpoint:
            return
        state = self.split_view.get_show_sidebar()
        self.window_settings.set_setting("sidebar-show", state)

