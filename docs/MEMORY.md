# Memory & prepare-cache lifecycle

Packed-GLB prepare writes temps; each open tab can hold an F3D/VTK engine.
This note is the contract so reopen / close / Flatpak do not leak disk or RAM.

Companion: [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md), [README §9](../README.md#9-preview-performance--memory), [SESSION_RESTORE.md](SESSION_RESTORE.md).

---

## Prepare cache

Implemented in `src/meshopt_decompress.py`:

| Cap | Value |
|-----|--------|
| Max entries | `MAX_PREPARE_CACHE_ENTRIES = 8` |
| Max bytes | `MAX_PREPARE_CACHE_BYTES = 256 MiB` |
| Key | `(realpath, mtime_ns, size, PREPARE_REVISION)` |
| Policy | LRU (`OrderedDict`, oldest first) |

Callers that keep a prepared path must call `release_prepared(path)` when done.
Last window close → `clear_prepare_cache()` (`LifecycleMixin.on_close_request`, only when no sibling `Viewer3dWindow` remains).

A single entry larger than the bytes cap is kept (cannot split); eviction still
runs for count/bytes after inserts.

---

## Contract (must not regress)

| Event | Must happen |
|-------|-------------|
| **Tab close** | Cancel in-flight warm load; `viewer.release_resources()`; clear tab `mesh_stats` / overlays |
| **`release_resources`** | Stop animation timer; `make_current` if realized; `scene.clear()`; release prepared temp; drop `camera` / `window` / `scene` / `engine` |
| **Warm load cancel** | If prepare already finished, free temps (idempotent); worker also frees if it finishes after cancel (`warm_load.py`) |
| **Last window close** | Tear down all tabs + Split Compare secondary viewer; `clear_prepare_cache()` |
| **Split Compare off** | `_teardown_split_compare_viewer` → `release_resources` on secondary viewer |

| Piece | Where |
|-------|--------|
| Tab close | `window_tabs.TabsMixin.on_tab_close_page` |
| Window close | `window_lifecycle.LifecycleMixin.on_close_request` |
| Warm load holder | `warm_load.py` + `window_load.LoadMixin` + `ViewerTab._warm_load_holder` |
| Engine teardown | `f3d_viewer_load.F3DLoadMixin.release_resources` |

Also: wrap tab close in `_switching_tab` and unbind scrubber / `notify::playing` before the page dies — avoids GObject handler-id warnings and double-bind with `notify::selected-page`.

---

## Historical bug (why this doc exists)

Closing a tab used to call a stub `release_resources` that only dropped prepare-cache retains.
Each tab’s **F3D `Engine` + VTK scene** stayed alive → RSS stuck near peak after close, then climbed again on reopen. `vtkDebugLeaks` reported multiple full engine graphs at process exit.

Measured under Flatpak with three ~150–180 MiB GLBs as tabs:

| Build | Peak RSS | After close tabs |
|-------|----------|------------------|
| Before teardown fix | ~1494 MiB | ~1495 MiB (no drop) |
| After | ~1495 MiB | ~420 MiB |

Open/close cycles (4× × 3 meshes): after-close RSS stabilizes (~417 → ~459 MiB). Treat **linear growth per cycle** as a regression; a flat residual vs never-loaded baseline (~100–160 MiB after the first engine) is normal (VTK/GL arenas).

---

## Warm-load + other temps

- Prepare runs off the main thread; `scene.add` stays on the main thread.
- Closing mid-prepare must release warm-holder temps.
- **Part hide** prefers an in-memory filtered GLB (`scene.add(bytes)`); no `exhibit-parts-*` file on success.
- Skin-weight heat temps (`exhibit-skinw-*`) are **not** prepare-cache managed; Inspect / load mixin unlinks them on disable or tab close.

Do not start many warm-loads in parallel — unselected tabs never realize GL.
See [SESSION_RESTORE.md](SESSION_RESTORE.md).

---

## How to measure

### Host pytest (temps / prepare cache / CPU)

[`tools/profile_pytest.py`](../tools/profile_pytest.py) — cProfile + tracemalloc + `/tmp/exhibit-*` leak scan. See [TESTING.md](TESTING.md).

Introspection: `prepare_cache_stats()` in `meshopt_decompress.py` (`entries`, `refs`, `orphans`, `bytes`).

Stale `exhibit-meshopt-*` under `/tmp` after a crash/GUI kill are normal until cleaned; the profiler `--clean-stale-temps` removes them. A green suite must leave **0 new** temps.

### Flatpak tab RSS (native F3D/VTK)

Script: [`tools/profile_tab_memory.py`](../tools/profile_tab_memory.py) (runs **inside** the Exhibit Flatpak; needs a display).

```sh
flatpak kill io.github.nokse22.Exhibit   # optional

EXHIBIT_MESH_DIR=/path/to/big/glbs \
EXHIBIT_PROFILE_FILES=3 \
EXHIBIT_SETTLE_S=3 \
flatpak run --filesystem=host --command=python3 io.github.nokse22.Exhibit \
  "$(pwd)/tools/profile_tab_memory.py"
```

Env: `EXHIBIT_MESH_DIR`, `EXHIBIT_PROFILE_FILES`, `EXHIBIT_SETTLE_S`, `EXHIBIT_LOAD_TIMEOUT_S`, optional `EXHIBIT_PATCHED_PKG` (host package root for A/B without rebuilding Flatpak).

Watch: `peak_rss_mib`, after-close / `final_rss_mib`, `alive_engines_in_tabs` (should be `0`), `prepare_cache_entries`.

Host unit tests cover prepare retain/release and warm-load cancel (`tests/test_meshopt_*`, `tests/test_warm_load.py`) but **cannot** catch native F3D/VTK RSS.

---

## Operational tips

- Prefer fewer simultaneous tabs for huge assets; each tab ≈ one F3D engine.
- Prepare cache is shared process-wide; open viewers retain their load path until close/reload.
- After Flatpak permission changes, fully quit (`flatpak kill io.github.nokse22.Exhibit`).
