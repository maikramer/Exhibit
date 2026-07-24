# window_object_tree.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Object-tree popover helpers extracted from Viewer3dWindow."""

from __future__ import annotations

from gettext import gettext as _
from gi.repository import Gio, GLib, GObject, Gtk, Pango

from .gltf_scene_graph import SceneTreeNode, tree_has_mesh


class ObjectTreeItem(GObject.Object):
    """GObject wrapper for a glTF scene node in the floating object tree."""

    __gtype_name__ = "ExhibitObjectTreeItem"

    def __init__(self, node: SceneTreeNode):
        super().__init__()
        self.index = int(node.index)
        self.name = node.name
        self.has_mesh = bool(node.has_mesh)
        self.children = [ObjectTreeItem(child) for child in node.children]


class ObjectTreeMixin:
    def _setup_object_tree_view(self):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_object_tree_setup)
        factory.connect("bind", self._on_object_tree_bind)
        factory.connect("unbind", self._on_object_tree_unbind)
        self.object_tree_view.set_factory(factory)
        empty = Gio.ListStore.new(ObjectTreeItem)
        self.object_tree_view.set_model(Gtk.NoSelection.new(empty))

    def _object_tree_child_model(self, item):
        if not isinstance(item, ObjectTreeItem) or not item.children:
            return None
        store = Gio.ListStore.new(ObjectTreeItem)
        for child in item.children:
            store.append(child)
        return store

    def refresh_object_tree(self):
        try:
            roots = self.f3d_viewer.get_scene_tree()
            available = tree_has_mesh(roots)
            self.object_tree_button.set_visible(available)

            if not available:
                self._scene_tree_roots = []
                empty = Gio.ListStore.new(ObjectTreeItem)
                self.object_tree_view.set_model(Gtk.NoSelection.new(empty))
                if (
                    self.object_tree_popover is not None
                    and self.object_tree_popover.get_visible()
                ):
                    self.object_tree_popover.popdown()
                return

            self._scene_tree_roots = [ObjectTreeItem(node) for node in roots]
            root_store = Gio.ListStore.new(ObjectTreeItem)
            for item in self._scene_tree_roots:
                root_store.append(item)

            tree_model = Gtk.TreeListModel.new(
                root_store,
                False,
                True,
                self._object_tree_child_model,
            )
            self.object_tree_view.set_model(Gtk.NoSelection.new(tree_model))
        except Exception as e:
            self.logger.error(f"Error while building object tree: {e}")
            self.object_tree_button.set_visible(False)

    def _on_object_tree_setup(self, factory, list_item):
        expander = Gtk.TreeExpander()
        expander.set_indent_for_icon(True)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        check = Gtk.CheckButton()
        label = Gtk.Label(xalign=0.0, hexpand=True)
        label.set_wrap(False)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(check)
        row.append(label)
        expander.set_child(row)
        list_item.set_child(expander)

    def _on_object_tree_bind(self, factory, list_item):
        tree_row = list_item.get_item()
        if tree_row is None:
            return
        item = tree_row.get_item()
        expander = list_item.get_child()
        expander.set_list_row(tree_row)

        row = expander.get_child()
        check = row.get_first_child()
        label = check.get_next_sibling()
        label.set_label(item.name)
        if item.has_mesh:
            label.remove_css_class("object-tree-structural")
        else:
            label.add_css_class("object-tree-structural")

        hidden = self.f3d_viewer.get_effective_hidden_part_indices()
        self._block_object_tree = True
        try:
            check.set_active(item.index not in hidden)
        finally:
            self._block_object_tree = False

        handler_id = check.connect(
            "notify::active", self.on_object_part_toggled, item.index
        )
        self._object_tree_check_handlers[id(check)] = handler_id

    def _on_object_tree_unbind(self, factory, list_item):
        expander = list_item.get_child()
        if expander is None:
            return
        row = expander.get_child()
        if row is None:
            return
        check = row.get_first_child()
        handler_id = self._object_tree_check_handlers.pop(id(check), None)
        if handler_id is not None:
            check.disconnect(handler_id)

    def on_object_part_toggled(self, check, _pspec, node_index):
        if self._block_object_tree:
            return
        if not self.f3d_viewer.set_part_visible(node_index, check.get_active()):
            self.send_toast(_("Couldn't update object visibility"))
            self._block_object_tree = True
            try:
                check.set_active(not check.get_active())
            finally:
                self._block_object_tree = False
            return
        # Ancestor hide expands via effective_hidden — refresh checkboxes.
        GLib.idle_add(self.refresh_object_tree)
