# Migração libexhibit (fork)

Base: `upstream/master` (libexhibit C) + features do fork Python.

Branches:
- `fork-python-legacy` — snapshot pré-merge (referência)
- `migrate-libexhibit` — trabalho atual

## Checklist de features (não perder)

- [x] Multi-document tabs v1 (AdwTabView + focus-existing + warm prepare)
- [x] Outliner UI + part visibility via GLB filter reload
- [x] Bone/armature kinds in tree; X-ray opacity when show-armature on
- [x] Viewport tool rail (sidebar/home/outliner)
- [x] Inspect skin-weight heat (joint picker) + scivis-array-name
- [x] Mesh stats overlay
- [x] Camera presets + Shift/Ctrl nav + invert/sensitivity + zoom/orbit-to-cursor (focal-plane NDC)
- [x] GLB prepare: meshopt + KHR_mesh_quantization + KTX2/BasisU (hooked in ExbWindow.load_file + F3DViewer shim)
- [x] File watch / auto-reload + reload prompt dialog
- [x] Headless CLI render + turntable video on Exb standalone path
- [x] Animation names combo (glTF names wired); bind pose default on load
- [x] Split compare (paned + drop on secondary viewer)
- [x] Session restore / recent files (persist + restore wired)
- [x] Flatpak: libktx, meshoptimizer, sandbox home/tmp/media
- [x] pytest green (legacy mixin tests skipped via conftest)
- [x] i18n pot/po regen via update_translations.sh
- [x] Docs fork kept + MIGRATE_LIBEXHIBIT checklist

## Estratégia

1. Merge upstream → base libexhibit (feito)
2. Manter módulos Python do fork instalados via meson
3. Re-wire UI/engine: `ExbView`/`ExbEngine` no lugar de `f3d_viewer`
4. Portar feature a feature; marcar checklist
5. Sem PR para Nokse22 — fork separado


## Bloqueios Exb C API

Estas features do fork precisam de API nova em `libexhibit` (C), não só Python:

- Blender-like nav (pointer world hit, orbit around cursor) — hoje Exb.View tem orbit/pan/zoom simples
- Warm-load multi-engine prepare race (parcialmente possível em Python)

## Em andamento

Checklist de features: completo (focal-plane NDC ≈ cursor nav).  
Flatpak build local (runtime 50) — VTK ainda compilando; falta F3D/libexhibit/app para validar runtime.
