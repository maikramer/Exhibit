# Testing (host, no Flatpak)

Unit / pipeline / structural tests for this fork. Most run **without Gtk, F3D, libmeshoptimizer, or libktx**. Goal: lock prepare/pack/stats/camera/CLI helpers and catch regressions on pure-Python paths.

CI: [`.github/workflows/pytest.yml`](../.github/workflows/pytest.yml).

## Run

```sh
python3 -m pip install pytest   # once
./tools/run_tests.sh
# or
python3 -m pytest tests/ -q
```

Useful filters:

```sh
./tools/run_tests.sh tests/test_cli_render_extended.py
./tools/run_tests.sh -k "orbit or prepare" -q
./tools/run_tests.sh --collect-only -q
```

Bootstrap: [`tests/conftest.py`](../tests/conftest.py) exposes `src/` as the `exhibit` package (no install required).

## Scale and layout

Rough order of magnitude: **~1300** collected tests (parametrize-heavy grids included).

| Area | Examples |
|------|----------|
| Vector / camera presets | `test_vector_math*`, `test_camera_views*`, `test_camera_orbit_grid.py` |
| Viewport nav math | `test_camera_nav.py` — see [NAVIGATION.md](NAVIGATION.md) |
| GLB prepare / meshopt / KTX2 | `test_meshopt_*`, `test_ktx2_*`, [`glb_factory.py`](../tests/glb_factory.py) |
| glTF graph / pack / outliner kinds | `test_gltf_scene_graph*` (kinds, armature split, hide helpers), `test_gltf_pack*` — [OUTLINER.md](OUTLINER.md) |
| Mesh stats | `test_mesh_stats*` |
| CLI render (headless) | `test_cli_render*` (parsers / jobs / options; no F3D) |
| Video encode helpers | `test_video_encode.py` |
| Session / paths | `test_session_*`, `test_path_utils`, `test_open_errors` — [SESSION_RESTORE.md](SESSION_RESTORE.md) |
| Window mixins (AST) | `test_window_*_mixin.py`, `test_window_init_helpers.py` |
| Split Compare / tabs / i18n | `test_window_tabs_split.py`, `test_window_tabs_context_menu.py`, `test_focus_existing_tab.py`, `test_help_overlay_i18n.py`, `test_potfiles.py` |
| Inspect / skins | `test_skin_weights.py`, `test_window_inspect_mixin.py` — [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md) |

Gtk/Adw template windows are usually checked **structurally** (AST / UI XML), not by launching the full app in CI.
Outliner overlay chrome (transparent panel over `GLArea`) is **manual Flatpak** —
host tests cover scene-graph kinds / hide bytes only.

Synthetic assets: [`tests/glb_factory.py`](../tests/glb_factory.py) — `plain_triangle_gltf`, `multipart_gltf`, `quantized_triangle_gltf`, `basisu_fallback_gltf`, translated/scaled/empty/non-indexed helpers, `write_glb` / `glb_bytes`.

## Philosophy

- **Do not assume green means correct.** New cases often expose real product bugs; keep tests that document broken behavior until fixed (or assert the broken path explicitly with `pytest.raises`).
- Prefer **parametrized matrices** (presets × up axes × distances) over one-off asserts when checking invariants.
- Native decode (`libmeshoptimizer` / `libktx`) is optional on the host: helpers and PNG/BasisU-fallback paths must stay testable without those libs (native tests **skip** when missing).

## Quirks / learnings locked by tests

### CLI `--up` and negative axes

`normalize_cli_argv` rewrites ``--up -Y`` → ``--up=-Y`` before argparse so
negative axes work either way:

```sh
exhibit render model.glb -o /tmp/out --up -Y
exhibit render model.glb -o /tmp/out --up=-Y
```

Coverage: `test_build_parser_up_choices` and
`test_build_parser_up_space_separated_negative_works` in
`tests/test_cli_render_extended.py`.

### CLI defaults (parity with GUI)

See `cli_render.DEFAULT_*`:

| Setting | Default |
|---------|---------|
| Background | `1,1,1` (white) |
| Grid | on (`--no-grid` to disable) |
| Light intensity | `1.8` (`DEFAULT_LIGHT_INTENSITY` — not imported from `settings_manager`, so parsers stay Gtk-free) |

### Prepare / pack

- External `.gltf` always needs prepare (pack → temp GLB).
- `_guess_image_mime` only returns **`image/*`** (or magic PNG/JPEG/KTX2); non-image mimetypes from the extension are ignored.
- Data-URI base64 uses `validate=True` → invalid payload → `MeshoptError`.
- Prepare pipeline order / KTX2 mip0 / `skin.skeleton`: [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md).

### Stats height

World AABB extent along scene up uses POSITION accessor `min`/`max` + node world matrices (lazy). Translation alone does not change height; scale on the up axis does.

### Packaging / i18n / session

1. **POTFILES** must list every `src/**/*.py` that uses `_()` / `ngettext`, but not helpers without i18n (`file_patterns.py`).
2. **Help overlay** strings must stay active in `Exhibit.pot` / `pt_BR.po` — msgmerge can obsolete them if pot is stale (`test_help_overlay_i18n.py`).
3. **Session restore** must queue opens — see [SESSION_RESTORE.md](SESSION_RESTORE.md) and `test_session_restore_queue.py`.

## Adding tests

1. Prefer factories in `glb_factory.py` over binary fixtures in-repo.
2. Call `clear_prepare_cache()` in setup/teardown (or an autouse fixture) when touching prepare/cache.
3. Keep F3D/Gtk out of unit tests; if a mixin needs them, test only pure helpers or use fakes (e.g. `_FakeCamera`).
4. After large `src/` or `tests/` moves: `graphify update .`.

## Profiling host pytest (CPU + alloc + temp leaks)

Stdlib profiler (no Flatpak/display):

```sh
./tools/profile_pytest.py                      # full suite → .profile/
./tools/profile_pytest.py --clean-stale-temps  # also unlink orphan /tmp/exhibit-*
./tools/profile_pytest.py -k prepare --top 40
./tools/profile_pytest.py --no-profile         # durations + leak scan only
```

Report covers: slowest tests, cProfile top, tracemalloc peak/sites, `/tmp/exhibit-*`
before/after, `prepare_cache_stats()` after suite. Optional UI: `snakeviz .profile/*.pstats`.

Session autouse in `tests/conftest.py` clears prepare cache at end and warns if the
run left **new** exhibit temps (stale temps from crashed GUI sessions are separate —
use `--clean-stale-temps`).

## Flatpak memory / tab RSS (not CI)

Native F3D/VTK RSS is invisible to host pytest. Use:

```sh
EXHIBIT_MESH_DIR=/path/to/big/glbs EXHIBIT_PROFILE_FILES=3 \
flatpak run --filesystem=host --command=python3 io.github.nokse22.Exhibit \
  "$(pwd)/tools/profile_tab_memory.py"
```

Expect a large drop peak → after closing tabs; `alive_engines_in_tabs=0`.
Contract and measured numbers: [MEMORY.md](MEMORY.md).

Warm-load cancel / prepare retain without Gtk: `tests/test_warm_load.py`, `tests/test_meshopt_*`.

## Related

- Docs index: [README.md](README.md)
- Feature overview: [../README.md](../README.md) (§ Tests, § CLI, §9)
- Memory teardown: [MEMORY.md](MEMORY.md)
- Prepare / inspect: [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md)
- Session restore: [SESSION_RESTORE.md](SESSION_RESTORE.md)
- Viewport navigation: [NAVIGATION.md](NAVIGATION.md)
- Historical A–E plan: [MELHORIAS_A_E.md](MELHORIAS_A_E.md)
