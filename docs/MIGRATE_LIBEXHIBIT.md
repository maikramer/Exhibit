# Migração libexhibit (fork)

Base: `upstream/master` (libexhibit C) + features do fork Python.

Branches:
- `fork-python-legacy` — snapshot pré-merge (referência)
- `migrate-libexhibit` — trabalho atual

## Checklist de features (não perder)

- [~] Multi-document tabs v1 (AdwTabView + focus-existing + warm prepare)
- [~] Outliner UI + part visibility via GLB filter reload
- [~] Bone/armature kinds in tree; X-ray via show-armature prop (partial)
- [~] Viewport tool rail (sidebar/home/outliner)
- [~] Inspect skin-weight heat (joint 0) + Exb scivis-array-name prop
- [~] Mesh stats overlay (label on GtkOverlay; needs polish)
- [~] Camera presets via Exb rotate; Blender touchpad nav still TODO
- [x] GLB prepare: meshopt + KHR_mesh_quantization + KTX2/BasisU (hooked in ExbWindow.load_file + F3DViewer shim)
- [~] File watch / auto-reload + reload prompt dialog
- [~] Headless CLI render (Exb standalone fallback); video encode still f3d-path
- [~] Animation names combo (glTF names wired); bind pose default on load
- [~] Split compare (paned + drop on secondary viewer)
- [~] Session restore / recent files (persist + restore wired)
- [x] Flatpak: libktx, meshoptimizer, sandbox home/tmp/media
- [~] pytest suite adapted for Exb shim; mixin UI tests still legacy
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

Flatpak build local (runtime 50) — VTK/F3D demora.
