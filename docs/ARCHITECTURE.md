# Architecture (fork)

Short map of how the gamedev fork is split. Feature details stay in topic docs.

---

## Window composition

`Viewer3dWindow` is a thin `Adw.ApplicationWindow` + mixins (~560 LOC glue).
Business logic lives in mixins / helpers under `src/`.

| Módulo | Mixin | Papel |
|--------|-------|-------|
| `window_tabs.py` | `TabsMixin` | Tabs, close teardown, sync cameras, **Split Compare** |
| `window_animation.py` | `AnimationMixin` | Clip combo / scrubber / keyframe marks |
| `window_object_tree.py` | `ObjectTreeMixin` | Canvas outliner overlay: kinds, eye visibility |
| `window_settings_ui.py` | `SettingsUIMixin` | Bindings switch/spin/color |
| `window_settings_io.py` | `SettingsIOMixin` | Presets / HDRI / thumb |
| `window_settings_react.py` | `SettingsReactMixin` | Reações a settings |
| `window_load.py` | `LoadMixin` | Open / drop / recent / session / warm-load (`warm_load.py`) |
| `window_layout.py` | `LayoutMixin` | Sidebar / breakpoint |
| `window_chrome.py` | `ChromeMixin` | Play / ortho / open external |
| `window_lifecycle.py` | `LifecycleMixin` | Close / home / session; `clear_prepare_cache` (última janela) |
| `window_inspect.py` | `InspectMixin` | Stats, armature, depth, normals, skin weights |
| `skin_weights.py` | (helpers) | Joint list + `WEIGHT_EXHIBIT` heat temps |
| `window_file_watch.py` | `FileWatchMixin` | Auto-reload / mtime |
| `window_export.py` | `ExportMixin` | Save PNG + toasts |
| `window_preferences.py` | `PreferencesMixin` | Preferences dialog / nav prefs |

Viewer stack: `widgets/f3d_viewer.py` + `f3d_viewer_load.py` (load mixin).
Prepare: `meshopt_decompress.py`, `ktx2_transcode.py`, `gltf_pack.py`, `gltf_scene_graph.py`.
Outliner row widget: `widgets/object_tree_row.py` — [OUTLINER.md](OUTLINER.md).

---

## Import rule (cycles)

Do **not** put openable-extension lists on `window.py`.
`LoadMixin` / `SettingsIOMixin` importing them created `window ↔ window_load`
cycles.

Shared lists live in `src/file_patterns.py` (`allowed_extensions`, `image_patterns`).

---

## Gtk.Template + mixins

PyGObject’s `@Gtk.Template` registration only scans **`CallThing` attributes on
the decorated class itself** — not mixin bases. Handlers declared with
`@Gtk.Template.Callback` on mixins (`LoadMixin`, `LayoutMixin`,
`LifecycleMixin`, …) stay unresolved.

When any `<signal handler="…">` in `window.ui` cannot be bound, GtkBuilder
aborts template setup and **silently discards every `<style>` / CSS class** in
that file. Symptom: Adwaita defaults everywhere (e.g. opaque `listview.view`
black slab over the outliner) even though `style.css` looks correct.

Fix in `src/window.py`:

1. `_hoist_template_callbacks(cls)` copies mixin `CallThing`s onto the class.
2. Apply the template **after** the class body:
   `Viewer3dWindow = Gtk.Template(resource_path=…)(_hoist_template_callbacks(Viewer3dWindow))`.

Do not move callbacks onto `Viewer3dWindow` only to “fix CSS” — keep them on
mixins and hoist. Runtime write-up:
[RUNTIME.md](RUNTIME.md#gtkbuilder-style-classes-vanish).

---

## Topic docs

| Doc | Topic |
|-----|--------|
| [OUTLINER.md](OUTLINER.md) | Canvas outliner: kinds, overlay, transparency |
| [RUNTIME.md](RUNTIME.md) | EGL/`create_external`, bind pose, template CSS, dense stats, file watch |
| [SPLIT_COMPARE.md](SPLIT_COMPARE.md) | Dual viewport, pin, swap, sash GSettings |
| [SESSION_RESTORE.md](SESSION_RESTORE.md) | Sequential open queue (GL realize) |
| [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md) | Prepare, KTX2 mip0, skin.skeleton, depth/glyphs/weights |
| [NAVIGATION.md](NAVIGATION.md) | Orbit/pan/zoom prefs |
| [MEMORY.md](MEMORY.md) | Prepare LRU, F3D teardown, RSS harness |
| [TESTING.md](TESTING.md) | Pytest layout / quirks |
| [FLATPAK.md](FLATPAK.md) | Build modules, pins, sandbox |
| [MELHORIAS_A_E.md](MELHORIAS_A_E.md) | Historical A–E plan + tick log |
| [README.md](README.md) | Index of this folder |

User-facing summary: root [README.md](../README.md).
