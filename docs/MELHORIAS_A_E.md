# Plano detalhado A–E — Exhibit fork

Goal do loop: entregar as cinco faixas do estudo + extras úteis no caminho.
Não editar o arquivo `.cursor/plans/estudo_melhorias_exhibit_*.plan.md`.

Ordem de execução: **B → A → D → E → C → extras**.

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

1. CI job `pytest` no GitHub Actions (rápido, sem Flatpak).
2. `vector_math` unit tests (grátis).
3. `clear_prepare_cache` no shutdown da app.
4. Script `tools/run_tests.sh`.

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

---

## Backlog A–E (plano inicial)

**Concluído** (itens 1–12). God nodes: `window.py` **560 LOC** + mixins abaixo (`window_tabs` 829); `f3d_viewer` **759** + `f3d_viewer_load` 441; prepare cache LRU+bytes; `file_patterns.py` quebra ciclos de import.

### Mapa de mixins (`Viewer3dWindow`)

| Módulo | Mixin | Papel |
|--------|-------|-------|
| `window_tabs.py` | `TabsMixin` | Tabs, warm-load, sync cameras, Split Compare |
| `window_animation.py` | `AnimationMixin` | Clip combo / scrubber |
| `window_object_tree.py` | `ObjectTreeMixin` | Hide/show mesh parts |
| `window_settings_ui.py` | `SettingsUIMixin` | Bindings switch/spin/color |
| `window_settings_io.py` | `SettingsIOMixin` | Presets / HDRI / thumb |
| `window_settings_react.py` | `SettingsReactMixin` | Reações a mudanças de settings |
| `window_load.py` | `LoadMixin` | Open / drop / recent / session |
| `window_layout.py` | `LayoutMixin` | Sidebar / breakpoint |
| `window_chrome.py` | `ChromeMixin` | Play / ortho / open external |
| `window_lifecycle.py` | `LifecycleMixin` | Close / home / restore toggle |
| `window_inspect.py` | `InspectMixin` | Stats HUD / armature X-ray |
| `window_file_watch.py` | `FileWatchMixin` | Auto-reload / mtime poll |
| `window_export.py` | `ExportMixin` | Save PNG + toasts |

### Arquivo — ondas 2–33 (concluídas)

Session/recent/Open Folder, sync cameras, CLI video/GIF, extracts de mixins,
About/metainfo/POTFILES, e **Split Compare** experimental completo (dual viewport,
pin, sash GSettings, restore silencioso, docs/i18n). Spike dual viewport → entregue
como `win.split-compare` / `Ctrl+Shift+D`.

### Loop — onda 34
1. ~~**Potfiles**~~ — `file_patterns.py` fora do POTFILES + teste negativo (tick #43).
2. ~~**Backlog hygiene**~~ — ticks/ondas antigas compactados (tick #43).
3. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 35
1. ~~**Swap models**~~ — `win.split-compare-swap` / `Ctrl+Shift+X` + botão (tick #44).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 36
1. ~~**Disable swap when identical**~~ — action desabilitada se paths iguais / pin ausente (tick #45).
2. ~~**i18n pot merge**~~ — Swap strings no pot + msgmerge nos `.po` (tick #45).
3. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 37
1. ~~**Tooltip dinâmico**~~ — botão Swap explica por que está desabilitado (tick #46).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 38
1. ~~**Pause feature streak**~~ — pytest verde; `window.py` 560 LOC; ciclos none (tick #47).
2. ~~**Bugfix**~~ — string help “reopen silently” restaurada no `pt_BR` (msgmerge tinha marcado obsolete).
3. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 39
1. ~~**Test help-overlay strings**~~ — `tests/test_help_overlay_i18n.py` (tick #48).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 40
1. ~~**Pause / README checklist**~~ — atalhos Split Compare em §7 (tick #49).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 41
1. ~~**Idle**~~ — pytest OK; `window.py` 560 LOC; ciclos none; sem regressão (tick #50).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 42
1. ~~**Idle**~~ — pytest OK; help-overlay i18n OK; sem bug (tick #51).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 43
1. ~~**Idle**~~ — pytest OK; sem bug (tick #52).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 44
1. ~~**Idle**~~ — pytest OK; sem bug (tick #53).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 45
1. ~~**Idle**~~ — pytest OK; sem bug (tick #54).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop — onda 46
1. ~~**Idle**~~ — pytest OK; loop `sleep 180` encerrado (tick #55).
2. ~~**Sem extract**~~ — salvo regressão.

### Loop
- **Parado** no tick #55 (backlog A–E + Split Compare entregues; só idle smoke).
- Reiniciar manualmente se houver novo backlog.
