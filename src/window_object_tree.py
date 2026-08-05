# window_object_tree.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Object-tree (Outliner) helpers extracted from Viewer3dWindow."""

from __future__ import annotations

from gettext import gettext as _
from gi.repository import Gio, GLib, GObject, Gtk

from .gltf_scene_graph import (
    SCENE_KIND_ARMATURE,
    SCENE_KIND_BONE,
    SCENE_KIND_EMPTY,
    SCENE_KIND_MESH,
    SceneTreeNode,
    tree_has_mesh,
)
from .widgets.object_tree_row import ObjectTreeRow

_ICON_RESOURCE_PREFIX = "/io/github/nokse22/Exhibit/icons/16x16/actions"
_KIND_ICON = {
    SCENE_KIND_MESH: f"{_ICON_RESOURCE_PREFIX}/outliner-mesh-symbolic.svg",
    SCENE_KIND_EMPTY: f"{_ICON_RESOURCE_PREFIX}/outliner-empty-symbolic.svg",
    SCENE_KIND_BONE: f"{_ICON_RESOURCE_PREFIX}/outliner-bone-symbolic.svg",
    SCENE_KIND_ARMATURE: f"{_ICON_RESOURCE_PREFIX}/outliner-armature-symbolic.svg",
}


class ObjectTreeItem(GObject.Object):
    """GObject wrapper for a glTF scene node in the outliner."""

    __gtype_name__ = "ExhibitObjectTreeItem"

    def __init__(self, node: SceneTreeNode):
        super().__init__()
        self.index = int(node.index)
        self.name = node.name
        self.has_mesh = bool(node.has_mesh)
        self.kind = node.kind or (
            SCENE_KIND_MESH if node.has_mesh else SCENE_KIND_EMPTY
        )
        self.children = [ObjectTreeItem(child) for child in node.children]

    @property
    def icon_resource(self) -> str:
        return _KIND_ICON.get(self.kind, _KIND_ICON[SCENE_KIND_EMPTY])

    @property
    def is_synthetic(self) -> bool:
        """Synthetic armature roots use negative indices."""
        return self.index < 0

    @property
    def can_toggle_visibility(self) -> bool:
        if self.kind == SCENE_KIND_ARMATURE or self.is_synthetic:
            return False
        if self.kind == SCENE_KIND_BONE:
            return False
        return True


class ObjectTreeMixin:
    def _setup_object_tree_view(self):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_object_tree_setup)
        factory.connect("bind", self._on_object_tree_bind)
        factory.connect("unbind", self._on_object_tree_unbind)
        self.object_tree_view.set_factory(factory)
        empty = Gio.ListStore.new(ObjectTreeItem)
        selection = Gtk.SingleSelection.new(empty)
        selection.set_autoselect(False)
        selection.set_can_unselect(True)
        self.object_tree_view.set_model(selection)
        self.object_tree_view.set_single_click_activate(False)
        # Panel paints no background; labels/icons stay fully opaque over the 3D view.
        self.object_tree_view.add_css_class("object-tree-view")
        panel = getattr(self, "object_tree_panel", None)
        if panel is not None:
            panel.set_opacity(1.0)
            panel.add_css_class("object-tree-panel")
            panel.add_css_class("object-tree-overlay-panel")
        scroll = self.object_tree_view.get_parent()
        while scroll is not None and not isinstance(scroll, Gtk.ScrolledWindow):
            scroll = scroll.get_parent()
        if scroll is not None:
            scroll.add_css_class("object-tree-scroll")

    def _object_tree_child_model(self, item):
        if not isinstance(item, ObjectTreeItem) or not item.children:
            return None
        store = Gio.ListStore.new(ObjectTreeItem)
        for child in item.children:
            store.append(child)
        return store

    def _set_object_tree_overlay_available(self, available: bool):
        # Whole shell (toggle + panel) only when active tree has meshes.
        shell = getattr(self, "object_tree_overlay_shell", None)
        toggle = getattr(self, "object_tree_toggle", None)
        if shell is not None:
            shell.set_visible(bool(available))
        if toggle is not None and not available:
            toggle.set_active(False)
        if available:
            sync = getattr(self, "_sync_object_tree_overlay_margin", None)
            if callable(sync):
                sync()

    def refresh_object_tree(self):
        try:
            roots = self.f3d_viewer.get_scene_tree()
            available = tree_has_mesh(roots)
            self._set_object_tree_overlay_available(available)
            if not available:
                self._scene_tree_roots = []
                empty = Gio.ListStore.new(ObjectTreeItem)
                selection = Gtk.SingleSelection.new(empty)
                selection.set_autoselect(False)
                selection.set_can_unselect(True)
                self.object_tree_view.set_model(selection)
                return

            self._scene_tree_roots = [ObjectTreeItem(node) for node in roots]
            root_store = Gio.ListStore.new(ObjectTreeItem)
            for item in self._scene_tree_roots:
                root_store.append(item)

            tree_model = Gtk.TreeListModel.new(
                root_store,
                False,
                False,  # hierarchy rows start collapsed
                self._object_tree_child_model,
            )
            selection = Gtk.SingleSelection.new(tree_model)
            selection.set_autoselect(False)
            selection.set_can_unselect(True)
            self.object_tree_view.set_model(selection)
        except Exception as e:
            self.logger.error(f"Error while building object tree: {e}")
            self._set_object_tree_overlay_available(False)

    def _on_object_tree_setup(self, factory, list_item):
        list_item.set_activatable(True)
        expander = Gtk.TreeExpander()
        expander.set_indent_for_icon(True)
        expander.add_css_class("object-tree-expander")

        row = ObjectTreeRow()
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
        if not isinstance(row, ObjectTreeRow):
            return

        hidden = self.f3d_viewer.get_effective_hidden_part_indices()
        can_toggle = item.can_toggle_visibility
        visible = True if not can_toggle else (item.index not in hidden)

        row.bind_item(
            name=item.name,
            kind=item.kind,
            icon_resource=item.icon_resource,
            node_index=item.index,
            depth=tree_row.get_depth(),
            visible=visible,
            can_toggle=can_toggle,
        )

        handler_id = row.connect(
            "visibility-toggled",
            self._on_object_tree_visibility,
            item.index,
        )
        self._object_tree_row_handlers[id(row)] = handler_id

    def _on_object_tree_unbind(self, factory, list_item):
        expander = list_item.get_child()
        if expander is None:
            return
        row = expander.get_child()
        if not isinstance(row, ObjectTreeRow):
            return
        handler_id = self._object_tree_row_handlers.pop(id(row), None)
        if handler_id is not None:
            row.disconnect(handler_id)

    def _on_object_tree_visibility(self, row: ObjectTreeRow, visible: bool, node_index: int):
        if self._block_object_tree:
            return
        if node_index < 0:
            return
        if not self.f3d_viewer.set_part_visible(node_index, visible):
            self.send_toast(_("Couldn't update object visibility"))
            self._block_object_tree = True
            try:
                row.eye.set_active(not visible)
                row.sync_eye_icon()
            finally:
                self._block_object_tree = False
            return
        # Row eye already matches; skip full TreeListModel rebuild (kept expand state).

    def on_object_part_toggled(self, check, _pspec, node_index):
        """Legacy entry point kept for tests / callers expecting checkbox API."""
        if self._block_object_tree:
            return
        if node_index < 0:
            return
        if not self.f3d_viewer.set_part_visible(node_index, check.get_active()):
            self.send_toast(_("Couldn't update object visibility"))
            self._block_object_tree = True
            try:
                check.set_active(not check.get_active())
            finally:
                self._block_object_tree = False
            return
        # No full refresh — same as _on_object_tree_visibility.
