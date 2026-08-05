# Plano detalhado A–E — Exhibit fork

**Status:** concluído (faixas A–E + Split Compare + extras). Loop 3 min **parado** no tick #55.

Docs vivos (arquitetura / features / learnings): [`docs/README.md`](README.md).
Este arquivo = histórico do plano + ticks. Não editar `.cursor/plans/estudo_melhorias_exhibit_*.plan.md`.

Ordem original: **B → A → D → E → C → extras**.

Docs de feature / lições (além deste plano): índice [`docs/README.md`](README.md).

| Doc | Assunto |
|-----|---------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Mixins, import rules, mapa de docs |
| [`INSPECT_AND_PREPARE.md`](INSPECT_AND_PREPARE.md) | Prepare, KTX2 mip0, skin.skeleton, depth/glyphs/skin-weights |
| [`SESSION_RESTORE.md`](SESSION_RESTORE.md) | Restore de abas: fila sequencial, anti-truncate GSettings |
| [`NAVIGATION.md`](NAVIGATION.md) | Orbit/pan/zoom, prefs, polo/gimbal, GTK pitfalls |
| [`SPLIT_COMPARE.md`](SPLIT_COMPARE.md) | Dual viewport, pin, swap |
| [`MEMORY.md`](MEMORY.md) | Prepare LRU + teardown F3D |
| [`RUNTIME.md`](RUNTIME.md) / [`FLATPAK.md`](FLATPAK.md) | Runtime Flatpak/F3D + pins de build |
| [`TESTING.md`](TESTING.md) | Pytest host |
| [`../README.md`](../README.md) | Features user-facing (inventário fork vs upstream) |
| [`MIGRATE_LIBEXHIBIT.md`](MIGRATE_LIBEXHIBIT.md) | Merge libexhibit + checklist PostFX / shell |

---

## B) Testes pipeline GLB

**Por quê:** único caminho puro-Python testável sem Gtk; desbloqueia refactors.

| Arquivo | Mudança |
|---------|---------|
| `tests/conftest.py` | `sys.path` → `src/` como pacote `exhibit` |
| `tests/glb_factory.py` | Build GLB sintético (triângulo, multipart, quantized) |
| `tests/test_meshopt_decompress.py` | `needs_*`, prepare cache, dequant, release |
| `tests/test_gltf_scene_graph.py` | tree, hide-nodes, skins, `_effective_hidden` |
| `tests/test_mesh_stats.py` | verts/faces/height/overlay |
| `tests/test_camera_views.py` | presets + orbit |
| `tests/test_cli_render.py` | parser, `_expand_view_jobs` (sem F3D) |
| `tests/test_ktx2_transcode.py` | PNG encode, basisu drop, needs_ktx2 |
| `pyproject.toml` | `[tool.pytest.ini_options]` |

**Done quando:** `python -m pytest tests/ -q` passa no host; meshopt nativo se `libmeshoptimizer` existir; KTX2 real skip se sem `libktx`.

---

## A) Split mínimo `window.py`

**Por quê:** 2283 LOC / 115 edges — god object.

| Extrair | Métodos-alvo | Novo arquivo |
|---------|--------------|--------------|
| Tabs | `_add_viewer_tab`, warm-load, close, bar, `_iter_tabs` | `src/window_tabs.py` (mixin `TabsMixin`) |
| Animation | combo, bind/unbind scrubber, keyframes | `src/window_animation.py` (`AnimationMixin`) |

`Viewer3dWindow(TabsMixin, AnimationMixin, Adw.ApplicationWindow)`.
Sem mudança de comportamento UI. Object tree / settings ficam pra round 2.

**Done quando:** app importa; tabs open/close/warm-load intactos; anim combo/scrubber intactos; LOC `window.py` cai ~400+.

---

## D) Robustez / UX runtime

| Item | Arquivo | Ação |
|------|---------|------|
| `except Exception: pass` | `src/widgets/f3d_viewer.py` | log warning via `logger_lib` (não engolir) |
| Prepare cache LRU | `src/meshopt_decompress.py` | cap N entradas + bytes; evict unreferenced |
| Erros prepare | `window.py` / toast path | mensagem clara `MeshoptError` vs genérico |

**Done quando:** cleanup falho aparece no log; cache tem `MAX_PREPARE_CACHE_*`; toast prepare legível.

---

## E) Perf

| Item | Ação |
|------|------|
| Prepare always-off-main | Warm path já existe; estender first-open GLB prepare em thread (loading page) |
| Cache LRU | Compartilha com D |
| Part-toggle | Manter rewrite bytes; skip re-prepare se `prepared_path` (já parcial) — documentar + test |

**Done quando:** first-open packed GLB não bloqueia UI no prepare; testes cobrem cache hit no part-toggle path.

---

## C) Feature gamedev

**Escolha default:** suporte **`.gltf` + bin/URI embutíveis** no prepare (empacota pra GLB temp) — alinhado à limitação README L54.

| Arquivo | Mudança |
|---------|---------|
| `meshopt_decompress.py` / novo `gltf_pack_embed.py` | Resolver buffers/imagens URI → GLB embutido |
| `needs_glb_prepare` / `prepare_*` | Aceitar `.gltf` |
| README | Atualizar limitação |
| Testes | fixture `.gltf` + `.bin` |

Compare side-by-side fica como extra futuro se tempo sobrar.

**Done quando:** abrir `.gltf` packed (meshopt/quant) no GUI/CLI sem converter manual.

---

## Extras (se aparecer no caminho)

1. ~~CI job `pytest` no GitHub Actions (rápido, sem Flatpak).~~ **feito**
2. ~~`vector_math` unit tests (grátis).~~ **feito**
3. ~~`clear_prepare_cache` no shutdown da app.~~ **feito** (`LifecycleMixin.on_close_request`, só última janela)
4. ~~Script `tools/run_tests.sh`.~~ **feito**
5. ~~Teardown F3D no tab close + cancel warm-load.~~ **feito** — ver [MEMORY.md](MEMORY.md)
6. ~~Harness RSS Flatpak.~~ **feito** — `tools/profile_tab_memory.py`

---

## Critérios globais

- Sem ciclos de import (graphify).
- `graphify update .` após mudanças em `src/`.
- Caveman commits só se usuário pedir.

---

## Status (loop)

| Faixa | Status | Entrega |
|-------|--------|---------|
| B testes | feito | `tests/` + `tools/run_tests.sh` + CI pytest |
| A split | feito | `window_tabs.py` + `window_animation.py` |
| D robustez | feito | LRU cache 8 + logs em `release_resources` |
| E perf | feito (já existia) | warm prepare off-main em todo open |
| C feature | feito | `gltf_pack.py` + prepare aceita `.gltf` |
| Extra | feito | CI pytest, `vector_math` tests, lazy `f3d`, `ObjectTreeMixin`, force `glb`/`gltf` filters, README testes |
| Ticks #1–30 | feito | extracts mixins, session/recent, sync cameras, CLI video/GIF, helpers |
| Tick 3min #31–42 | feito | Split Compare (dual viewport, pin, sash, restore) + docs/i18n/About |
| Tick 3min #43 | feito | POTFILES hygiene + backlog compactado |
| Tick 3min #44 | feito | Split Compare Swap (`Ctrl+Shift+X`) |
| Tick 3min #45 | feito | Swap disable se paths iguais + msgmerge |
| Tick 3min #46 | feito | Tooltip dinâmico do botão Swap |
| Tick 3min #47 | feito | Smoke LOC/pytest; fix i18n help reopen |
| Tick 3min #48 | feito | Test help-overlay msgids no pot / não obsolete |
| Tick 3min #49 | feito | README checklist Split Compare shortcuts |
| Tick 3min #50 | feito | Idle smoke: pytest OK, LOC 560, ciclos none |
| Tick 3min #51 | feito | Idle smoke + help-overlay i18n ainda OK |
| Tick 3min #52 | feito | Idle smoke pytest OK |
| Tick 3min #53 | feito | Idle smoke pytest OK |
| Tick 3min #54 | feito | Idle smoke pytest OK |
| Tick 3min #55 | feito | Idle smoke; loop 3min encerrado (backlog vazio) |
| Session restore queue | feito | Fila sequencial + anti-truncate GSettings; doc `docs/SESSION_RESTORE.md`; testes `test_session_restore_queue.py` |
| Onda 47 | feito | Prefs modal, theme menu, nav clássica + Alt, polo/gimbal, `docs/NAVIGATION.md` |
| Expansão testes + docs | feito | Suite ~1300; `docs/TESTING.md`; índice `docs/README.md`; README CLI `--up=` / defaults |
| Inspect / prepare onda | feito | KTX2 level0, skin.skeleton, depth/glyphs patches F3D, skin weights; `docs/INSPECT_AND_PREPARE.md` |

---

## Backlog A–E (plano inicial)

**Concluído** (itens 1–12). God nodes: `window.py` **560 LOC** + mixins abaixo (`window_tabs` 829); `f3d_viewer` **759** + `f3d_viewer_load` 441; prepare cache LRU+bytes; `file_patterns.py` quebra ciclos de import.

### Mapa de mixins (`Viewer3dWindow`)

| Módulo | Mixin | Papel |
|--------|-------|-------|
| `window_tabs.py` | `TabsMixin` | Tabs, close teardown, sync cameras, Split Compare |
| `window_load.py` | `LoadMixin` | Open / drop / recent / session / warm-load (`warm_load.py`, fila `_pending_open_paths`) |
| `window_animation.py` | `AnimationMixin` | Clip combo / scrubber |
| `window_object_tree.py` | `ObjectTreeMixin` | Hide/show mesh parts |
| `window_settings_ui.py` | `SettingsUIMixin` | Bindings switch/spin/color |
| `window_settings_io.py` | `SettingsIOMixin` | Presets / HDRI / thumb |
| `window_settings_react.py` | `SettingsReactMixin` | Reações a mudanças de settings |
| `window_layout.py` | `LayoutMixin` | Sidebar / breakpoint |
| `window_chrome.py` | `ChromeMixin` | Play / ortho / open external |
| `window_lifecycle.py` | `LifecycleMixin` | Close / home / restore; `clear_prepare_cache` (última janela) |
| `window_preferences.py` | `PreferencesMixin` | Preferences dialog, theme menu, nav gschema |
| `window_inspect.py` | `InspectMixin` | Stats HUD, armature, depth, normals, skin weights |
| `skin_weights.py` | (helpers) | Joint list + `WEIGHT_EXHIBIT` heat temps |
| `window_file_watch.py` | `FileWatchMixin` | Auto-reload / mtime poll |
| `window_export.py` | `ExportMixin` | Save PNG + toasts |
| `camera_nav.py` | (helpers) | Orbit/dolly/polar clamp; `NAV_SETTING_DEFAULTS` |

### Entregas pós-plano (resumo ondas 2–46)

Session/recent/Open Folder, sync cameras, CLI video/GIF, extracts de mixins,
About/metainfo/POTFILES, **Split Compare** (dual viewport / pin / sash / swap),
idle smoke até tick #55. Detalhe: [SPLIT_COMPARE.md](SPLIT_COMPARE.md).

### Loop — pós tick #55
1. ~~**Session restore bug**~~ — warm-loads paralelos deixavam abas unrealized + truncavam `session-files` no meio do restore. Fix: fila `_pending_open_paths` + `_advance_open_queue` + persist só com batch idle. Doc: [`SESSION_RESTORE.md`](SESSION_RESTORE.md). Testes: `tests/test_session_restore_queue.py`.

### Loop — onda 47 (nav / prefs / theme)
1. ~~**Prefs modal**~~ — `AdwPreferencesDialog`; Navigation/Loading/folders; removed sidebar More tab.
2. ~~**Theme header**~~ — dropdown `MenuButton` + `Gio.Menu` (Follow/Light/Dark; avoid missing `dark-mode-symbolic`).
3. ~~**Touchpad nav**~~ — Blender-like orbit/pan/zoom; scroll/dolly clamps; kinetic off.
4. ~~**Classic orbit**~~ — default `nav-orbit-around-cursor=false`; pivot=focal; Alt toggles cursor mode.
5. ~~**Pole unstick**~~ — `elevation_axis` fallback + `clamp_camera_polar` (no hard gimbal freeze at top).
6. ~~**GTK wiring**~~ — header home/prefs/theme via `connect` / actions (Template.Callback CallThing pitfalls).
7. ~~**Docs**~~ — [`NAVIGATION.md`](NAVIGATION.md) + README §8/8b.

### Loop — docs / testes (pós onda 47)
1. ~~**Expansão pytest**~~ — matrizes camera/vector/meshopt/pack/stats/CLI; ~1300 collected.
2. ~~**Quirk CLI `--up`**~~ — eixos negativos exigem `--up=-Y` (argparse); README + [`TESTING.md`](TESTING.md).
3. ~~**Docs índice**~~ — [`docs/README.md`](README.md) cobre ARCHITECTURE / SPLIT / SESSION / INSPECT / NAV / MEMORY / RUNTIME / FLATPAK / TESTING.
4. ~~**Memory teardown docs**~~ — [`MEMORY.md`](MEMORY.md) com contrato + números A/B + harness Flatpak; README §9 / Tests + TESTING.md.

### Loop — inspect / prepare (pós A–E)
1. ~~**KTX2 level0**~~ — `GetImageOffset` (mips smallest-first).
2. ~~**skin.skeleton**~~ — `ensure_skin_skeletons` no prepare (armature F3D).
3. ~~**Display Depth**~~ — patch F3D lineariza Z (evita branco).
4. ~~**Normal glyphs**~~ — patch world-space + `Glyph Scale`.
5. ~~**Skin Weights**~~ — scivis `WEIGHTS_0` + bone heat `WEIGHT_EXHIBIT`.
6. ~~**Docs**~~ — [`INSPECT_AND_PREPARE.md`](INSPECT_AND_PREPARE.md) + README §4 + metainfo.

### Loop
- Backlog A–E + Split Compare + session restore + nav/prefs + inspect/prepare + testes/docs + memory docs entregues.
- Reiniciar manualmente se houver novo backlog.

### Docs de produto
| Doc | Conteúdo |
|-----|----------|
| `README.md` (raiz) | Features fork, quick start, build/test |
| [`docs/README.md`](README.md) | Índice desta pasta |
| [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) | Mixins + mapa de docs |
| [`docs/TESTING.md`](TESTING.md) | Pytest host + harness RSS Flatpak |
| [`docs/MEMORY.md`](MEMORY.md) | Prepare LRU, teardown F3D/tab, números A/B, `profile_tab_memory.py` |
| [`docs/NAVIGATION.md`](NAVIGATION.md) | Controles, GSettings `nav-*`, aprendizados (polo, template, clamps) |
| [`docs/SESSION_RESTORE.md`](SESSION_RESTORE.md) | Fila de open / restore de sessão |
| [`docs/SPLIT_COMPARE.md`](SPLIT_COMPARE.md) | Dual viewport / pin / swap |
| [`docs/RUNTIME.md`](RUNTIME.md) | EGL / loading / anim gotchas |
| [`docs/FLATPAK.md`](FLATPAK.md) | Pins F3D/VTK, sandbox |
| [`docs/INSPECT_AND_PREPARE.md`](INSPECT_AND_PREPARE.md) | Prepare order, KTX2 mip0, skin.skeleton, overlays |
| `docs/MELHORIAS_A_E.md` | Plano A–E + status de ondas (este arquivo) |

---

## Aprendizados (pós A–E)

### Memory / F3D por tab

Tab close que só dava `release_prepared` **não** liberava Engine VTK → RSS ficava no peak (~1.5 GiB).
Contrato: `release_resources` (scene + engine + anim timer), cancel warm-load, `clear_prepare_cache` na última janela.
Residual ~100–160 MiB após o 1º engine é normal; crescimento linear por ciclo = regressão.
Doc + números: [MEMORY.md](MEMORY.md). Harness: `tools/profile_tab_memory.py`.

### Session restore paralelo

Warm-load seleciona a aba alvo pro GLArea mapear. Abrir N paths em paralelo = só a última realiza; `session-files` truncava mid-restore.
Fila sequencial + testes: [SESSION_RESTORE.md](SESSION_RESTORE.md).
