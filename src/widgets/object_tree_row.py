# object_tree_row.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Custom outliner row widget (Blender-like) for the object tree."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Gdk, GObject, Graphene, Gtk, Pango

from ..gltf_scene_graph import (
    SCENE_KIND_ARMATURE,
    SCENE_KIND_BONE,
    SCENE_KIND_EMPTY,
    SCENE_KIND_MESH,
)

_KIND_LABEL = {
    SCENE_KIND_MESH: lambda: _("Mesh"),
    SCENE_KIND_EMPTY: lambda: _("Empty"),
    SCENE_KIND_BONE: lambda: _("Bone"),
    SCENE_KIND_ARMATURE: lambda: _("Armature"),
}

# Accent bars (r, g, b, a) — Blender-ish cues.
_KIND_ACCENT = {
    SCENE_KIND_MESH: (0.35, 0.62, 0.95, 1.0),
    SCENE_KIND_EMPTY: (0.55, 0.55, 0.58, 0.9),
    SCENE_KIND_BONE: (0.92, 0.72, 0.28, 1.0),
    SCENE_KIND_ARMATURE: (0.95, 0.55, 0.22, 1.0),
}


class ObjectTreeRow(Gtk.Widget):
    """Outliner row: eye toggle, type icon, name, kind badge; custom snapshot."""

    __gtype_name__ = "ExhibitObjectTreeRow"

    __gsignals__ = {
        "visibility-toggled": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self):
        super().__init__()
        self.set_css_name("objecttreerow")
        self.add_css_class("object-tree-row")
        self.set_layout_manager(
            Gtk.BoxLayout(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=6,
            )
        )

        self._kind = SCENE_KIND_EMPTY
        self._depth = 0
        self._node_index = 0
        self._block = False
        self._eye_handler = 0

        self.eye = Gtk.ToggleButton()
        self.eye.set_valign(Gtk.Align.CENTER)
        self.eye.set_focus_on_click(False)
        self.eye.set_has_frame(False)
        self.eye.add_css_class("flat")
        self.eye.add_css_class("circular")
        self.eye.add_css_class("object-tree-eye")
        self.eye.set_tooltip_text(_("Toggle visibility"))
        self.eye.set_parent(self)

        self.icon = Gtk.Image(pixel_size=16)
        self.icon.set_valign(Gtk.Align.CENTER)
        self.icon.add_css_class("object-tree-icon")
        self.icon.set_parent(self)

        self.name_label = Gtk.Label(
            xalign=0.0,
            hexpand=True,
            ellipsize=Pango.EllipsizeMode.END,
        )
        self.name_label.set_valign(Gtk.Align.CENTER)
        self.name_label.add_css_class("object-tree-name")
        self.name_label.set_parent(self)

        self.badge = Gtk.Label()
        self.badge.set_valign(Gtk.Align.CENTER)
        self.badge.add_css_class("object-tree-badge")
        self.badge.set_parent(self)

        self._eye_handler = self.eye.connect("toggled", self._on_eye_toggled)

    def do_dispose(self):
        for child in (self.eye, self.icon, self.name_label, self.badge):
            if child is not None and child.get_parent() is self:
                child.unparent()
        Gtk.Widget.do_dispose(self)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        height = self.get_height()
        if self.get_width() <= 0 or height <= 0:
            return

        # Kind accent strip on the leading edge (custom paint).
        accent = _KIND_ACCENT.get(self._kind, _KIND_ACCENT[SCENE_KIND_EMPTY])
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = accent
        bar = Graphene.Rect()
        bar.init(0, 2, 3.0, max(1.0, height - 4))
        snapshot.append_color(rgba, bar)

        # Hierarchy guide ticks in the TreeExpander indent zone (negative x).
        # Expander leaves a gutter; paint faint vertical rails into it.
        if self._depth > 0:
            guide = Gdk.RGBA()
            guide.red = guide.green = guide.blue = 0.55
            guide.alpha = 0.28
            for level in range(self._depth):
                x = -12.0 * (self._depth - level) + 4.0
                tick = Graphene.Rect()
                tick.init(x, 0, 1.0, float(height))
                snapshot.append_color(guide, tick)

        child = self.get_first_child()
        while child is not None:
            self.snapshot_child(child, snapshot)
            child = child.get_next_sibling()

    def bind_item(
        self,
        *,
        name: str,
        kind: str,
        icon_resource: str,
        node_index: int,
        depth: int,
        visible: bool,
        can_toggle: bool,
    ) -> None:
        self._kind = kind or SCENE_KIND_EMPTY
        self._depth = max(0, int(depth))
        self._node_index = int(node_index)

        for css in (
            "kind-mesh",
            "kind-empty",
            "kind-bone",
            "kind-armature",
        ):
            self.remove_css_class(css)
            self.name_label.remove_css_class(css)
            self.badge.remove_css_class(css)
            self.icon.remove_css_class(css)
        kind_css = f"kind-{self._kind}"
        self.add_css_class(kind_css)
        self.name_label.add_css_class(kind_css)
        self.badge.add_css_class(kind_css)
        self.icon.add_css_class(kind_css)

        self.name_label.set_label(name)
        self.icon.set_from_resource(icon_resource)
        badge_fn = _KIND_LABEL.get(self._kind, _KIND_LABEL[SCENE_KIND_EMPTY])
        self.badge.set_label(badge_fn())

        self._block = True
        try:
            self.eye.set_sensitive(can_toggle)
            self.eye.set_active(bool(visible) if can_toggle else True)
            self.sync_eye_icon()
            if can_toggle:
                self.eye.remove_css_class("object-tree-eye-locked")
            else:
                self.eye.add_css_class("object-tree-eye-locked")
        finally:
            self._block = False

        self.queue_draw()

    def sync_eye_icon(self) -> None:
        if self.eye.get_active():
            self.eye.set_icon_name("view-reveal-symbolic")
        else:
            self.eye.set_icon_name("view-conceal-symbolic")

    def _on_eye_toggled(self, button: Gtk.ToggleButton) -> None:
        self.sync_eye_icon()
        if self._block:
            return
        self.emit("visibility-toggled", button.get_active())

    @property
    def node_index(self) -> int:
        return self._node_index
