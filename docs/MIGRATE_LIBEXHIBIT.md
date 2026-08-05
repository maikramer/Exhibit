# Migração libexhibit (fork)

Base: `upstream/master` (libexhibit C) + features do fork Python.

Branches:
- `fork-python-legacy` — snapshot pré-merge (referência)
- `migrate-libexhibit` — trabalho atual

## Checklist de features (não perder)

- [~] Multi-document tabs v1 (AdwTabView + focus-existing); warm load TODO
- [~] Outliner UI wired; part visibility awaits Exb API
- [~] Bone/armature kinds in tree; X-ray via show-armature prop (partial)
- [~] Viewport tool rail (sidebar/home/outliner)
- [~] Inspect entry + skins detect; heat-map awaits Exb buffer API
- [~] Mesh stats overlay (label on GtkOverlay; needs polish)
- [~] Camera presets via Exb rotate; Blender touchpad nav still TODO
- [x] GLB prepare: meshopt + KHR_mesh_quantization + KTX2/BasisU (hooked in ExbWindow.load_file + F3DViewer shim)
- [~] File watch / auto-reload (single-doc; prompt UI TODO)
- [~] Headless CLI render (Exb standalone fallback); video encode still f3d-path
- [~] Animation names combo (glTF names wired); bind pose default on load
- [ ] Split compare
- [~] Session restore / recent files (persist + restore wired)
- [x] Flatpak: libktx, meshoptimizer, sandbox home/tmp/media
- [~] pytest suite adapted for Exb shim; mixin UI tests still legacy
- [ ] i18n pt_BR + fork strings (POTFILES updated; pot regen TODO)
- [x] Docs fork kept + MIGRATE_LIBEXHIBIT checklist

## Estratégia

1. Merge upstream → base libexhibit (feito)
2. Manter módulos Python do fork instalados via meson
3. Re-wire UI/engine: `ExbView`/`ExbEngine` no lugar de `f3d_viewer`
4. Portar feature a feature; marcar checklist
5. Sem PR para Nokse22 — fork separado


## Bloqueios Exb C API

Estas features do fork precisam de API nova em `libexhibit` (C), não só Python:

- Part visibility / outliner hide (scene buffers / node hide)
- Skin-weight heat maps (in-memory GLB reload)
- Blender-like nav (pointer world hit, orbit around cursor) — hoje Exb.View tem orbit/pan/zoom simples
- Warm-load multi-engine prepare race (parcialmente possível em Python)

## Em andamento

Flatpak build local (runtime 50) — VTK/F3D demora.
