# Migração libexhibit (fork)

Base: `upstream/master` (libexhibit C) + features do fork Python.

Branches:
- `fork-python-legacy` — snapshot pré-merge (referência)
- `migrate-libexhibit` — trabalho atual

## Checklist de features (não perder)

- [ ] Multi-document tabs + warm load + focus-existing
- [ ] Outliner / object tree (multipart GLB visibility)
- [ ] Bone/armature kinds + X-ray skeleton
- [ ] Viewport tool rail / chrome header
- [ ] Inspect overlays + skin-weight heat maps
- [ ] Mesh stats overlay
- [ ] Blender-like touchpad navigation + camera presets
- [x] GLB prepare: meshopt + KHR_mesh_quantization + KTX2/BasisU (hooked in ExbWindow.load_file + F3DViewer shim)
- [ ] File watch / reload prompt
- [ ] Headless CLI render + video encode
- [ ] Animation names combo + default bind pose
- [ ] Split compare
- [ ] Session restore / recent files
- [x] Flatpak: libktx, meshoptimizer, sandbox home/tmp/media
- [ ] pytest suite + CI
- [ ] i18n pt_BR + fork strings
- [ ] Docs fork (ARCHITECTURE, OUTLINER, NAVIGATION, …)

## Estratégia

1. Merge upstream → base libexhibit (feito)
2. Manter módulos Python do fork instalados via meson
3. Re-wire UI/engine: `ExbView`/`ExbEngine` no lugar de `f3d_viewer`
4. Portar feature a feature; marcar checklist
5. Sem PR para Nokse22 — fork separado
