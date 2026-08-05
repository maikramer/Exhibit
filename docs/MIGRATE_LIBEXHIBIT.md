# Migração libexhibit (fork)

Base: `upstream/master` (libexhibit C) + features do fork Python.

Branches:
- `fork-python-legacy` — snapshot pré-merge (referência)
- `main` — trabalho atual

## Regra de shell

**Upstream shell / fork extension** — ver [ARCHITECTURE.md](ARCHITECTURE.md).

- Layout viewport + HeaderBar + Exb binds: igual upstream
- Tabs / outliner / Split Compare / Inspect / Recent: **declarados em `window.ui`**
- Proibido: `_setup_exb_tabs`, `_setup_minimal_outliner`, `_ensure_split_compare_chrome`
- Seed permitido: `_seed_primary_tab()` (ExbView → tab 0)

## Checklist de features (estado real)

Legenda: `[x]` ok · `[~]` parcial · `[ ]` faltando

- [x] Multi-document tabs (`AdwTabView` + focus-existing + warm prepare)
- [x] TabBar / TabView / Split / outliner **no `.ui`** (shell declarativo)
- [x] Tab bar + menu RMB (Close / Other / Left / Right / Reopen)
- [x] Outliner UI + part visibility via GLB filter reload
- [x] Bone/armature kinds; X-ray via InspectMixin
- [x] Header upstream (sidebar / home / menu) + ThemeSwitcher
- [x] Inspect UI (Scene → Inspect)
- [~] Normal glyphs / depth: props Exb + patches Flatpak
- [x] Mesh stats overlay (Gtk HUD)
- [x] Camera pose get/set Exb (Sync Cameras)
- [x] Nav: invert/sensitivity + zoom/orbit-to-cursor
- [x] GLB prepare: meshopt + quantization + KTX2/BasisU
- [x] File watch / auto-reload
- [x] Headless CLI render + turntable video
- [x] Animation names do glTF; bind pose default (**None**)
- [~] Animation keyframe marks (stub scale)
- [x] Split Compare no `.ui` (paned + Pin + Swap)
- [x] Session restore / recent files
- [x] Flatpak: libktx, meshoptimizer, sandbox
- [~] pytest: suite legado parcialmente skipped
- [x] Docs ARCHITECTURE + este checklist

## Estratégia

1. Merge upstream → base libexhibit (feito)
2. Manter módulos Python do fork via meson
3. Shell mergeável: estender `.ui`, não reparent em runtime
4. Shim `F3DViewer` fino até mixins falarem Exb direto (fora deste ciclo)
5. Sem PR para Nokse22

## API Exb C adicionada no fork

- `scivis-array-name`
- `normal-glyphs` / `normal-glyphs-scale`
- `exb_engine_get_camera_state` / `exb_engine_set_camera_state`
- Nav no view: invert / sensitivities / orbit-around-cursor / NDC zoom
- PostFX (`exb-postfx`): `bloom*` + `godrays*` → `final-shader`; SSAO params via F3D patch (`ao-radius` / `ao-bias` / `ao-kernel-size` / `ao-intensity`)

## Verificação

- Flatpak local (runtime 50) via `repo-migrate`
- Smoke: 2 modelos → abas; outliner; Inspect; Split Compare (`Ctrl+Shift+D`)
- Push só quando pedido
