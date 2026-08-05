# Outliner (object tree overlay)

Blender-like scene hierarchy over the 3D viewport. Companion to
[INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md) (part-hide reload) and
[ARCHITECTURE.md](ARCHITECTURE.md) (window mixins / template CSS).

---

## UX

- Sidebar / home stay on the **HeaderBar** (upstream chrome). Outliner is a
  floating **list** toggle on the canvas (`object_tree_overlay_shell`) — not a
  header popover and not a sidebar page.
- Toggle opens a `GtkRevealer` (slide-right) with the tree panel, top-aligned
  with the toggle (below the HeaderBar via measured `margin-top`).
- Whole shell is visible only when the active tab’s glTF tree has at least one
  mesh (`tree_has_mesh`).
- Hierarchy rows start **collapsed** (`TreeListModel` `passthrough=False`,
  `autoexpand=False`).
- Eye toggles visibility for **mesh** / **empty** nodes. Bones and synthetic
  armature roots are locked (no hide).
- Panel background is fully transparent so the GL model shows through; labels and
  icons stay opaque (`text-shadow` for contrast).

Widgets: `src/window.ui` (`viewport_overlay` → shell / toggle / revealer /
`object_tree_panel` / `object_tree_view`).

---

## Scene kinds

`SceneTreeNode` in `src/gltf_scene_graph.py` carries `kind`:

| Kind | Meaning |
|------|---------|
| `mesh` | Node with a mesh |
| `empty` | Transform / empty (no mesh) |
| `bone` | Joint in a skin hierarchy |
| `armature` | Synthetic root grouping a skin’s joints |

`build_scene_tree` keeps object nodes and skinned joints separate: pure joints
are omitted from the object branch and appear under an **Armature** root
(negative synthetic index). Icons:
`data/icons/16x16/actions/outliner-{mesh,empty,bone,armature}-symbolic.svg`
(registered in `exhibit.gresource.xml` + `Gtk.IconTheme` resource path).

---

## UI stack

| Piece | Role |
|-------|------|
| `ObjectTreeMixin` (`window_object_tree.py`) | Model refresh, selection, eye → hide |
| `ObjectTreeItem` | GObject wrapper (`kind`, `can_toggle_visibility`) |
| `ObjectTreeRow` (`widgets/object_tree_row.py`) | Custom row: eye, icon, name, kind badge, accent strip |
| `Gtk.TreeListModel` + `Gtk.SingleSelection` | Hierarchy + selection |
| CSS `.object-tree-*` (`data/style.css`) | Transparent panel / scroll / listview / rows |

---

## Part hide

Eye off strips `mesh` from hidden nodes and reloads via `scene.add(bytes)`
(`build_glb_hiding_nodes_bytes`). No `exhibit-parts-*` temp on the happy path.
Details and VTK `force_reader` notes: [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md#part-hide--in-memory-glb-f3d-35).

Flatpak keeps `F3D_MODULE_UI=OFF` — ImGui `ui.scene_hierarchy` is unused; this
Gtk overlay owns visibility ([FLATPAK.md](FLATPAK.md)).

---

## Transparency over `Gtk.GLArea`

Lessons locked while shipping the overlay:

1. CSS `alpha(@window_bg_color, …)` often composites as an opaque dark slab over
   `GLArea` (theme paint wins).
2. `widget.set_opacity(0.x)` on the whole panel does composite over GL, but also
   fades text and icons — unusable for an outliner.
3. Correct approach: **no fill** on panel / scrolledwindow / viewport / listview
   `.view` / rows (explicit `background: transparent`), keep content opacity at
   `1.0`, use `text-shadow` for readability. Hover / selection may use light
   `alpha(black, …)` only on the row under the pointer.

If the panel suddenly paints solid black again while CSS looks correct, check
that `.ui` `<style>` classes are actually applied — unresolved template
callbacks make GtkBuilder drop every style class (see
[RUNTIME.md](RUNTIME.md#gtkbuilder-style-classes-vanish) and
[ARCHITECTURE.md](ARCHITECTURE.md#gtktemplate--mixins)).

---

## Tests

- Host: `tests/test_gltf_scene_graph.py`, `tests/test_gltf_scene_graph_extended.py`
  (kinds, armature split, hide helpers).
- Full overlay chrome needs Flatpak + a multipart / skinned GLB (manual).
