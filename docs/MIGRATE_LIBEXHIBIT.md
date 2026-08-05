# Migração libexhibit (fork)

Base: `upstream/master` (libexhibit C) + features do fork Python.

Branches:
- `fork-python-legacy` — snapshot pré-merge (referência)
- `migrate-libexhibit` — trabalho atual

## Checklist de features (não perder)

- [~] Multi-document tabs v1 (AdwTabView + focus-existing); warm load TODO
- [~] Outliner UI wired; part visibility awaits Exb API
- [~] Bone/armature kinds in tree; X-ray via show-armature prop (partial)
- [ ] Viewport tool rail / chrome header
- [ ] Inspect overlays + skin-weight heat maps
- [~] Mesh stats overlay (label on GtkOverlay; needs polish)
- [ ] Blender-like touchpad navigation + camera presets
- [x] GLB prepare: meshopt + KHR_mesh_quantization + KTX2/BasisU (hooked in ExbWindow.load_file + F3DViewer shim)
- [~] File watch / auto-reload (single-doc; prompt UI TODO)
- [~] Headless CLI render (Exb standalone fallback); video encode still f3d-path
- [~] Animation names combo (glTF names wired); bind pose still TODO on Exb
- [ ] Split compare
- [ ] Session restore / recent files
- [x] Flatpak: libktx, meshoptimizer, sandbox home/tmp/media
- [ ] pytest suite + CI
- [ ] i18n pt_BR + fork strings
- [x] Docs fork kept + MIGRATE_LIBEXHIBIT checklist

## Estratégia

1. Merge upstream → base libexhibit (feito)
2. Manter módulos Python do fork instalados via meson
3. Re-wire UI/engine: `ExbView`/`ExbEngine` no lugar de `f3d_viewer`
4. Portar feature a feature; marcar checklist
5. Sem PR para Nokse22 — fork separado
