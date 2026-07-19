# viewer_tab.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Gtk

from .f3d_viewer import F3DViewer


class ViewerTab(Gtk.Overlay):
    """One document page: F3D viewer + optional stats HUD."""

    def __init__(self):
        super().__init__()
        self.filepath = ""
        self.file_name = ""
        self.mesh_stats = None
        self.armature_xray_restore = None
        self.loaded = False

        self.viewer = F3DViewer()
        self.viewer.add_css_class("f3d-render")
        self.viewer.set_hexpand(True)
        self.viewer.set_vexpand(True)
        self.set_child(self.viewer)

        self.stats_overlay_label = Gtk.Label(
            visible=False,
            halign=Gtk.Align.START,
            valign=Gtk.Align.END,
            margin_start=16,
            margin_bottom=16,
            xalign=0,
            selectable=True,
        )
        self.stats_overlay_label.add_css_class("stats-overlay")
        self.add_overlay(self.stats_overlay_label)

    def clear_overlays(self) -> None:
        self.stats_overlay_label.set_visible(False)
        self.stats_overlay_label.set_label("")
