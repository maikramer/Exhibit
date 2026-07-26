# Inspect overlays & GLB prepare — notes

Durable notes for gamedev preview (packed GLBs, armatures, debug viz).
Companion to the [README](../README.md) feature list.

---

## Prepare pipeline (order matters)

On `.glb` / `.gltf` open, `prepare_glb_for_load` may rewrite a temp when needed.
Rough order:

1. Pack external `.gltf` → self-contained GLB (`gltf_pack.py`) when URIs need embedding.
2. Decode **meshopt** compression + expand **mesh quantization**.
3. Transcode **KTX2 / BasisU** → PNG (`ktx2_transcode.py`) when no raster fallback.
4. Fill missing **`skin.skeleton`** (`ensure_skin_skeletons` in `gltf_scene_graph.py`).
5. Cache by `(realpath, mtime, size[, …])` + prepare revision; callers `release_prepared`.

Cache key includes a prepare revision so behavior fixes (e.g. skeleton fill) bust stale temps.
LRU caps: **8** entries / **256 MiB** (`MAX_PREPARE_CACHE_*`). Tab/window teardown: [MEMORY.md](MEMORY.md).

---

## Learnings

### KTX2 / BasisU — read level 0, not byte 0

After `ktxTexture2_TranscodeBasis`, mip levels are often stored **smallest-first**.
Reading RGBA from offset `0` yields garbage (wrong mip).

Use `ktxTexture2_GetImageOffset` / `GetImageSize` / `GetRowPitch` for **level 0**.
Regression: dense UASTC assets (e.g. VibeGame `moss_rock_lod0.glb`).

### Armature invisible on gltfpack skins

VTK/F3D only builds armature actors when `skin.skeleton >= 0`.
gltfpack often omits optional `skeleton` even when `joints` exist.

Prepare infers a skeleton root and writes it before load. If an already-open temp
still lacks it, Inspect → Show Armature may reload once.

### Display Depth washed white until zoom

F3D `display_depth` samples the **nonlinear** GL depth buffer (`0…1`).
With a typical near/far ratio, mesh depths cluster near `1.0` → white / flat.

This fork patches F3D (`build-aux/patches/f3d-linearize-display-depth.patch`):
linearize with camera near/far, remap to `[0,1]`, invert so **near = bright**.

Also force **opaque** mesh when depth is on (translucent geometry is skipped by
the depth pass — X-ray armature left a blank frame).

Mutual exclusion: depth disables normal glyphs and skin-weights overlays.

### Normal glyphs = porcupine

Stock F3D 3.5 sizes glyphs from **screen/FOV** (~15% of view height), so zooming
into a dense character turns every vertex into a thick spike.

Patches (`f3d-normal-glyphs-scale.patch`):

- World-space size ≈ **0.45% of geometry diagonal** × `model.normal_glyphs.scale`
- Expose scale to libf3d / Exhibit **Glyph Scale** spin (default `0.5`)

Glyphs still draw **per vertex** — dense LODs stay busy; lower Glyph Scale.

First paint after toggle may need a camera nudge if the GL area has not redrawn yet.

### Exact edge counts on dense meshes

Unique-edge sets are O(faces) in Python. For primitives with more than
**750 000** indices (voxel / marching-cubes intermediates), stats use the
approximate `faces × 1.5` estimate instead of stalling the UI.

### Skin weights

F3D exposes `WEIGHTS_0` / `JOINTS_0` as point arrays.

| Mode | Behavior |
|------|----------|
| Magnitude / Slot 0–3 | Scivis on `WEIGHTS_0` (no geometry reload) |
| Bone heat | Temp GLB with scalar `WEIGHT_EXHIBIT` for the selected `skin.joints` index |

Heat temps use prefix `exhibit-skinw-` and are **not** prepare-cache managed.
`F3DLoadMixin._release_load_path` unlinks them; Inspect clears window pointers on disable / tab close.

### Part hide — in-memory GLB (F3D 3.5)

Object-tree checkboxes strip `mesh` from hidden nodes (`build_glb_hiding_nodes_bytes`)
and reload via `scene.add(bytes)` — no `exhibit-parts-*` temp on the happy path.

VTK builds older than the stream auto-detect cutoff need `scene.force_reader=GLB`
for buffers. Exhibit sets it only for the buffer add, then clears it (Python
bindings lack `options.reset`; fallback rebuilds options without that key).

`F3D_MODULE_UI` / ImGui `ui.scene_hierarchy` stays **off** in Flatpak — Gtk tree
owns part visibility. Details: [FLATPAK.md](FLATPAK.md).

### Animation keyframes

Scrubber marks come from `scene.get_animation_keyframes()` after clip change /
load (`window_animation.py`). Empty list → no marks (no animations or API missing).

---

## UI map (sidebar → Scene → Inspect)

| Control | Setting key | Notes |
|---------|-------------|-------|
| Show Armature | `armature-enable` | X-ray opacity + thicker bones |
| Checkerboard | `checkerboard-enable` | UV check; reload |
| Normal Glyphs | `normal-glyphs` | Disables depth |
| Glyph Scale | `normal-glyphs-scale` | World-space multiplier |
| Display Depth | `display-depth` | Linearized colormap; opaque mesh |
| Skin Weights | `skin-weights` | Modes + joint combo |
| Weights Mode | `skin-weights-mode` | `magnitude` / `slot0`…`slot3` / `bone` |
| Joint | `skin-weights-joint` | Bone-heat only |
| Show Stats | `stats-overlay` | Gtk HUD + optional F3D filename info |

Code: `src/window_inspect.py`, `src/skin_weights.py`, settings in `settings_manager.py`.

---

## Flatpak F3D pin

See [FLATPAK.md](FLATPAK.md) for the full stack (VTK 9.6.2, libwebp, modules).

- Tag **v3.5.0** (`bcfa8d525cec…`) in `build-aux/libf3d.json`
- F3D patches: `f3d-linearize-display-depth.patch`, `f3d-normal-glyphs-scale.patch`
- WebP module requires bundled **libwebp** (not provided by GNOME Sdk CMake)

After changing patches or filesystem permissions: quit fully
(`flatpak kill io.github.nokse22.Exhibit`) then rebuild/reopen.

---

## Tests (host)

See [TESTING.md](TESTING.md) for the full suite. Focused inspect/prepare:

```sh
./tools/run_tests.sh
# focused:
python3 -m pytest tests/test_skin_weights.py tests/test_ktx2_transcode.py \
  tests/test_gltf_scene_graph.py tests/test_window_inspect_mixin.py -q
```

Full GUI overlays need Flatpak + a skinned GLB (e.g. bandit LOD with meshopt/KTX2).
