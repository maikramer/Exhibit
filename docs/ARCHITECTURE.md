# Architecture (fork)

Short map of how the gamedev fork is split. Feature details stay in topic docs.

---

## Shell rule (merge-friendly)

**Upstream owns the shell.** Fork extends it — does not rebuild it in `__init__`.

| Layer | Owns | Must not |
|-------|------|----------|
| Upstream | `window.ui` HeaderBar / ToolbarView / ExbView+Engine binds, ThemeSwitcher in menu | — |
| Fork UI | Extra ids in the **same** `window.ui` (TabBar, TabView, outliner overlay, Split Compare paned, Inspect/Loading/Recent) | Reparent ToolbarView tree at runtime |
| Fork Python | Mixins + thin `F3DViewer` shim | `_setup_*` that invent chrome widgets |

Allowed one-shot seed: `_seed_primary_tab()` moves template `ExbView` into tab 0. No TabView/outliner/split construction in Python.

```text
toolbar_view
├── top: header_bar          (sidebar + home + menu; floating overlay-button)
├── top: tab_bar             (fork, visible only when n_pages > 1)
└── content: toast_overlay
    └── split_compare_main_paned
        ├── start: viewport_overlay
        │   ├── child: tab_view
        │   ├── overlay: loading_status_page
        │   └── overlay: object_tree_overlay_shell  (outliner toggle + panel only)
        └── end: split_compare_revealer
```

Outliner shell sits below the HeaderBar: `TabsMixin._sync_object_tree_overlay_margin`
measures `header_bar` height when content extends under the header.

---

## Window composition

`ExbWindow` = thin `Adw.ApplicationWindow` + mixins. Glue in [`src/window.py`](../src/window.py):
declarative shell init, settings wire, actions, HDRI, ThemeSwitcher.

| Módulo | Mixin | Papel |
|--------|-------|-------|
| `window_tabs.py` | `TabsMixin` | Tabs, close teardown, sync cameras, **Split Compare** (widgets from `.ui`) |
| `window_animation.py` | `AnimationMixin` | Clip combo / scrubber / keyframe marks |
| `window_object_tree.py` | `ObjectTreeMixin` | Outliner ListView (ids from `.ui`) |
| `window_settings_ui.py` | `SettingsUIMixin` | Bindings switch/spin/color |
| `window_settings_io.py` | `SettingsIOMixin` | Presets / HDRI / thumb |
| `window_settings_react.py` | `SettingsReactMixin` | Reações a settings |
| `window_load.py` | `LoadMixin` | Open / drop / recent / session / warm-load |
| `window_layout.py` | `LayoutMixin` | Sidebar / breakpoint |
| `window_chrome.py` | `ChromeMixin` | Play / ortho / open external |
| `window_lifecycle.py` | `LifecycleMixin` | Close / home / session |
| `window_inspect.py` | `InspectMixin` | Stats, armature, depth, normals, skin weights |
| `window_file_watch.py` | `FileWatchMixin` | Auto-reload / mtime |
| `window_export.py` | `ExportMixin` | Save PNG + toasts |
| `window_preferences.py` | `PreferencesMixin` | Preferences / nav prefs |

Viewer API for multi-tab: thin shim [`widgets/f3d_viewer.py`](../src/widgets/f3d_viewer.py) over `Exb.View` / `Exb.Engine`.
Prepare: `meshopt_decompress.py`, `ktx2_transcode.py`, `gltf_pack.py`, `gltf_scene_graph.py`.

---

## Import rule (cycles)

Do **not** put openable-extension lists on `window.py`.
Shared lists: `src/file_patterns.py` (`allowed_extensions`, `image_patterns`).

---

## Gtk.Template + mixins

PyGObject’s `@Gtk.Template` only scans **`CallThing` on the decorated class**.
Mixin `@Gtk.Template.Callback` handlers must be hoisted:

1. `_hoist_template_callbacks(cls)`
2. `ExbWindow = Gtk.Template(…)(_hoist_template_callbacks(ExbWindow))`

See [RUNTIME.md](RUNTIME.md#gtkbuilder-style-classes-vanish).

---

## Topic docs

| Doc | Topic |
|-----|--------|
| [MIGRATE_LIBEXHIBIT.md](MIGRATE_LIBEXHIBIT.md) | Migration checklist |
| [OUTLINER.md](OUTLINER.md) | Canvas outliner |
| [RUNTIME.md](RUNTIME.md) | EGL, bind pose, template CSS |
| [SPLIT_COMPARE.md](SPLIT_COMPARE.md) | Dual viewport |
| [SESSION_RESTORE.md](SESSION_RESTORE.md) | Sequential open queue |
| [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md) | Prepare + inspect |
| [NAVIGATION.md](NAVIGATION.md) | Orbit/pan/zoom prefs |
| [MEMORY.md](MEMORY.md) | Prepare LRU / teardown |
| [TESTING.md](TESTING.md) | Pytest |
| [FLATPAK.md](FLATPAK.md) | Build / sandbox |
| [README.md](README.md) | Index |

User-facing summary: root [README.md](../README.md).
