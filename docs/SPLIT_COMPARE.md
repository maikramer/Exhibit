# Split Compare (experimental)

Side-by-side second F3D viewport for comparing models without leaving the window.
Complements **Sync Cameras Across Tabs** (`Ctrl+Shift+C`).

User checklist also lives in [README §7](../README.md#7-multi-document-tabs).

---

## Shortcuts / UI

| Action | Binding / control |
|--------|-------------------|
| Toggle Split Compare | `Ctrl+Shift+D` / Settings menu |
| Pin secondary model | checkbox in the secondary column |
| Swap active ↔ pinned | `Ctrl+Shift+X` / **Swap** button |
| Resize columns | drag sash on `split_compare_main_paned` |

Layout: horizontal paned — `AdwTabView` (start) | revealer column (end).
Secondary viewer is created **lazily** on first enable (extra F3D engine ≈ RAM).

---

## Behavior

1. **Follow mode (no pin):** secondary loads the active tab’s model; camera follows active.
2. **Pin:** secondary keeps a fixed filepath while you switch tabs; camera still follows active.
3. **Swap:** prefers selecting an existing tab that already has the pinned path; otherwise reloads the active tab with `override=True`. Pin becomes the previous active path.
4. **Options sync:** `_update_all_viewers_options` (and armature) also update the secondary viewer.
5. **Swap enable:** disabled when Split off, not pinned, paths identical, or pin file missing. Button tooltip explains why.

Restore on next launch is **silent** (no toast).

---

## GSettings

| Key | Type | Role |
|-----|------|------|
| `split-compare-enabled` | `b` | Reopen Split Compare after models load |
| `split-compare-sash-ratio` | `d` | Primary width fraction (0.45–0.80), debounce 300 ms |
| `split-compare-pinned` | `b` | Pin was on |
| `split-compare-pin-path` | `s` | Absolute pin path; cleared if missing on restore |

Schema: `data/io.github.nokse22.Exhibit.gschema.xml`.

---

## Code map

| Symbol / file | Role |
|---------------|------|
| `TabsMixin` (`window_tabs.py`) | toggle, pin, swap, sash, restore, load secondary |
| `LifecycleMixin` | teardown + persist enabled on close |
| `camera_sync.iter_camera_sync_peers(..., extras=)` | include secondary in camera sync |
| `tests/test_window_tabs_split.py` | structural / UI contract |
| `tests/test_help_overlay_i18n.py` | help overlay msgids stay in pot (not obsolete) |

---

## Learnings

- **Do not** put shared constants (`allowed_extensions`) in `window.py` — mixins importing them create `window ↔ window_load` cycles. Use `file_patterns.py`.
- **msgmerge** can mark still-used UI strings `#~ obsolete` if they are missing from `Exhibit.pot`. Keep pot in sync; guard with `test_help_overlay_i18n.py`.
- Dual viewport costs **+1 F3D engine**; keep lazy-create + teardown on disable/close.
- Pin path restore must `os.path.isfile` before re-pinning.
