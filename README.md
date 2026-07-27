<img height="128" src="data/icons/hicolor/scalable/apps/io.github.nokse22.Exhibit.svg" align="left"/>

# Exhibit (fork)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![made-with-python](https://img.shields.io/badge/Made%20with-Python-ff7b3f.svg)](https://www.python.org/)

Fork of **Exhibit** for a **gamedev asset workflow**: open packed GLBs from gltfpack-style pipelines, flip animation clips, hide mesh parts, inspect armatures / normals / depth / skin weights, and batch-render views for AI review — without leaving the desktop.

Powered by [F3D](https://github.com/f3d-app/f3d) (glTF, USD, STL, FBX, OBJ, PLY, and more).

<br clear="left"/>

## Credits

- **Original app:** [Nokse22/Exhibit](https://github.com/Nokse22/Exhibit) by [Nokse](https://github.com/Nokse22) — GPLv3.
- **Renderer:** [F3D](https://github.com/f3d-app/f3d) — BSD-3-Clause (see F3D license notes for bundled libs).
- **This fork:** [maikramer/Exhibit](https://github.com/maikramer/Exhibit) — gamedev-focused changes on top of upstream.
- In the app: **Help → About** lists the same fork summary, GitHub link, and upstream acknowledgement. Bug reports for this fork: [maikramer/Exhibit issues](https://github.com/maikramer/Exhibit/issues).

Upstream Flathub build (original app, not this fork):  
https://flathub.org/apps/io.github.nokse22.Exhibit

App ID stays `io.github.nokse22.Exhibit` so local Flatpak / GSettings stay compatible with upstream installs.

---

## Fork features (vs upstream)

| Area | What this fork adds |
|------|---------------------|
| **GLB prepare** | Expand meshopt + mesh quantization; transcode KTX2/BasisU → PNG; fill missing `skin.skeleton` |
| **Animation** | Clip combo with default **None** (bind pose); in-place clip switch; reimport when returning to None; **keyframe marks** on scrubber |
| **Parts** | Object tree hide/show; filtered GLB via F3D `scene.add(bytes)` (no parts temp on happy path) |
| **Inspect** | Armature X-ray, UV checkerboard, normal glyphs (+ scale), linearized depth, skin-weight heat maps, stats HUD |
| **File watch** | On-disk edits → silent reload (active tab) or `(modified)` + prompt |
| **Tabs** | Multi-document `AdwTabView`: each open/drop adds a tab; shared sidebar; same startup loading UI |
| **Compare** | **Sync Cameras** + experimental **Split Compare** (side-by-side column, Pin, Swap; shortcuts below) |
| **Recent** | Welcome page lists recent models (GSettings); drop a folder to open all GLB/glTF |
| **Session** | Optionally restore last open tabs on startup (Loading → **Restore Last Session**); opens are queued one tab at a time so each GLArea can realize |
| **UI** | Follow OS theme/accent (Yaru/Adwaita portal); Scene-tab IA (Animation + Inspect); glass chrome over the viewport |
| **CLI** | `exhibit render` → multi-angle PNGs + optional turntable `--video` + `manifest.json` (+ inspect flags) |
| **Perf** | Cached prepare (LRU ≤8 / 256 MiB); warm open (prepare ∥ F3D engine); tab/window teardown frees engines; ~60 Hz anim tick |
| **Flatpak** | F3D **3.5.0** / VTK **9.6.2**; EXR + WebP; `libmeshoptimizer` + `libktx` + `libwebp`; depth/glyph + VTK patches — [docs/FLATPAK.md](docs/FLATPAK.md) |

Topic docs: [docs/README.md](docs/README.md).

### 1. Packed GLB preparation (before F3D load)

F3D/VTK/Assimp cannot load several common packed-glTF extensions. On `.glb` open (GUI and CLI), the fork rewrites a temporary file when needed:

1. **`EXT_meshopt_compression` / `KHR_meshopt_compression`** — decode with `libmeshoptimizer` (filters: NONE, OCTAHEDRAL, QUATERNION, EXPONENTIAL, COLOR). Destination buffers are padded to a multiple of 4 so meshopt filters do not overrun (gltfpack LOD meshes).
2. **`KHR_mesh_quantization`** — expand quantized `POSITION` / `NORMAL` / `TANGENT` / `TEXCOORD_*` accessors to float and strip the extension.
3. **`KHR_texture_basisu` (KTX2 / BasisU)** — via `libktx`:
   - if the texture already has a PNG/JPEG `source` fallback → keep it and drop the BasisU extension;
   - otherwise decode the KTX2 image to PNG, rewrite the GLB, and strip `KHR_texture_basisu` from `extensionsUsed` / `extensionsRequired`.
   - After Basis transcode, **level 0** is read via `ktxTexture2_GetImageOffset` (mips may be smallest-first — do not assume RGBA starts at byte 0).
4. **`skin.skeleton`** — if a skin has `joints` but omits optional `skeleton` (common after gltfpack), prepare infers a root so F3D/VTK can build armature actors.

Prepared temps are **cached** by `(realpath, mtime, size, prepare_revision[, …])` with an **LRU** cap (max **8** entries / **256 MiB** on disk) so reopen / part-toggle / CLI batches do not re-decode every time. Callers that retain a prepared path must `release_prepared()`; tab close and last-window shutdown also flush via `clear_prepare_cache()` (see [docs/MEMORY.md](docs/MEMORY.md)).

Self-contained `.glb` and external `.gltf` + URI buffers/images (local or `data:`) are supported. Remote `http(s)` URIs are not.

### 2. Animation clips by name

- Sidebar → Scene → **Active animation** is an `AdwComboRow` fed by F3D `get_animation_names` (plus **None** and **All animations**).
- Default is **None** (empty `scene.animation.indices`) so the mesh stays in bind/rest pose until a clip is selected. Fresh opens reset to None; reloads keep the current clip.
- Selecting a clip updates `scene.animation.indices` and scrubber bounds **in place** (play/scrub enabled). Returning to **None** reimports the prepared GLB so the skin returns to bind pose — clearing indices alone leaves the last posed frame (F3D/VTK quirk).
- Scrubber shows **keyframe marks** from F3D `get_animation_keyframes` for the current selection.
- Details: [docs/RUNTIME.md](docs/RUNTIME.md#animation-none--bind-pose).

### 3. Object tree (multipart visibility)

- Header **list** button (next to home/reset) opens a popover with the glTF node hierarchy.
- Checkboxes hide/show mesh parts. Hidden nodes lose their `mesh` in a filtered GLB; reload keeps **camera and animation time**.
- With F3D 3.5 the filtered GLB is loaded from **memory** (`scene.add(bytes)`), not an `exhibit-parts-*` temp. Buffer loads may set `scene.force_reader=GLB` briefly on older VTK (cleared afterward).
- Flatpak keeps `F3D_MODULE_UI=OFF` — ImGui `ui.scene_hierarchy` is unused; the Gtk tree owns part visibility ([docs/INSPECT_AND_PREPARE.md](docs/INSPECT_AND_PREPARE.md)).
- Demo asset: [Cesium Milk Truck](https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/CesiumMilkTruck) (GLB).

### 4. Inspect overlays (Scene → Inspect)

Asset-review tools in the sidebar. Depth and normal glyphs conflict (depth pass hides overlays); enabling one turns the other off. Skin weights also yield to depth.

| Control | What it does |
|---------|----------------|
| **Show Armature** | F3D skeleton + X-ray mesh (thicker bones, opacity ~0.35). Needs glTF skins; may reload if `skin.skeleton` was missing. CLI: `--armature`. |
| **Checkerboard** | Replace textures with a UV checker (reload). |
| **Normal Glyphs** | Vertex normal arrows. Sized in **world space** (F3D patch); use **Glyph Scale** if still too dense. |
| **Display Depth** | Depth colormap with **linearized** Z (F3D patch). Forces opaque mesh — translucent X-ray would render blank. |
| **Skin Weights** | Color by `WEIGHTS_0` (magnitude / slot 0–3) or **Bone heat** (per-joint scalar via temp GLB). Joint combo lists `skin.joints` names. |
| **Show Stats** | Gtk HUD: height (m, +Y AABB), verts / faces / edges, scene counts. CLI: `stats` in `manifest.json`; `--overlay` burns into PNGs. |

Stats/height come from the **prepared** GLB when prepare ran. Height is lazy from POSITION `min`/`max` + node world matrices (Three.js-style AABB), not a full vertex scan.

Implementation notes and failure modes: [docs/INSPECT_AND_PREPARE.md](docs/INSPECT_AND_PREPARE.md).

### 5. Headless CLI render (`exhibit render`)

No Gtk window. Multi-angle PNGs + `manifest.json` for agent / review pipelines.

```sh
# Default 6 views → /tmp/hero-views/*.png + manifest.json
flatpak run io.github.nokse22.Exhibit render ./hero.glb -o /tmp/hero-views

# X-ray armature + orbit turntable PNGs
flatpak run io.github.nokse22.Exhibit render ./hero.glb -o /tmp/hero-rig \
  --armature --orbit 8 --size 1024x1024

# Same orbit frames → MP4 (needs ffmpeg on PATH)
flatpak run io.github.nokse22.Exhibit render ./hero.glb -o /tmp/hero-rig \
  --orbit 24 --video mp4 --video-fps 24

# Stats burned into PNGs + JSON stats block
flatpak run io.github.nokse22.Exhibit render ./hero.glb -o /tmp/hero-views \
  --overlay --views front,isometric

# UV checker / normals / depth (F3D 3.5 inspect)
flatpak run io.github.nokse22.Exhibit render ./hero.glb -o /tmp/hero-uv \
  --checkerboard --views isometric

# Custom views / animation pose
flatpak run io.github.nokse22.Exhibit render ./hero.glb -o /tmp/hero-views \
  --views front,isometric --animation-index 0 --animation-time 0.5
```

Stdout prints the absolute path to `manifest.json` (one line) for piping.

| Flag | Purpose |
|------|---------|
| `-o` / `--output` | Output directory (required) |
| `--views` | `front,right,back,left,top,isometric` (default: all six); can include `orbit` |
| `--orbit N` | Add N yaw steps around the model |
| `--size WxH` | Default `1024x1024` |
| `--up` | Scene up: `+Y` (default), `+X`, `-X`, `+Z`, … — **use `--up=-Y` (equals form) for negative axes**; `--up -Y` is rejected by argparse |
| `--armature` | Skeleton X-ray defaults |
| `--checkerboard` | Replace textures with UV checkerboard |
| `--normal-glyphs` | Draw vertex normals as arrows |
| `--display-depth` | Render depth buffer as grayscale (linearized in this fork) |
| `--opacity` / `--line-width` | Override mesh opacity / edge width |
| `--edges` | Show mesh edges |
| `--grid` / `--no-grid` | Ground grid (default **on**, matches GUI) |
| `--bg R,G,B` | Background 0..1 (default `1,1,1` — white, matches GUI) |
| `--animation-index` / `--animation-time` | Clip index + time in seconds |
| `--overlay` | Burn mesh stats into PNGs |
| `--format png` | Only PNG for now |
| `--video mp4\|webm\|gif` | Turntable video (`ffmpeg` for mp4/webm; Pillow GIF; auto-GIF if ffmpeg missing). Flatpak: uses host `ffmpeg` via `flatpak-spawn --host` when sandbox PATH has none |
| `--video-fps N` | Turntable frame rate (default `24`) |

Manifest includes model path, whether prepare ran, skins/animation names, `stats`, options used, view files, and optional `video` filename.

### 6. Multi-document tabs

- Opening or dropping another model while one is already loaded creates a **new tab** (file dialog supports multi-select).
- Drop a **folder** (or multiple files), or use **Open Folder** (`Ctrl+Shift+O`), to open every supported GLB/glTF in new tabs.
- Welcome page shows **Recent** models (persisted in GSettings), with **Clear Recent**.
- **Restore Last Session** (sidebar Loading, default on) reopens the previous tabs on startup unless a file is passed on the command line; turn off to clear saved session paths.
  - Paths live in GSettings `session-files` (absolute paths, existing files only).
  - Batch opens (session restore, Open Folder, multi-drop) are **queued**: one warm-load finishes before the next tab starts. Parallel warm-loads leave unselected tabs unrealized (stuck on Loading…) and used to truncate the saved session mid-restore — see [`docs/SESSION_RESTORE.md`](docs/SESSION_RESTORE.md).
  - Cap: first `DEFAULT_MAX_BATCH_OPEN` (24) models; toast when truncated.
- Settings menu → **Sync Cameras Across Tabs** keeps peer-tab cameras matched while you navigate.
- **Split Compare (Experimental)** checklist (details: [`docs/SPLIT_COMPARE.md`](docs/SPLIT_COMPARE.md)):
  - `Ctrl+Shift+D` — toggle side-by-side secondary F3D column (drag sash to resize; width remembered)
  - **Pin secondary model** — keep another file while switching tabs (camera still follows the active tab; pin path restored on next launch if the file exists)
  - `Ctrl+Shift+X` — **Swap** active tab ↔ pinned model
  - Split Compare + pin reopen quietly on the next launch when left on
- First file: no tab bar. Second file: same startup **Loading…** page, then the model appears and the tab bar reveals with both documents.
- Sidebar settings apply across tabs; animation scrubber / object tree follow the **active** tab.
- Closing a tab cancels any in-flight warm load, calls `release_resources()` on that tab’s F3D viewer (scene clear + drop engine), and clears overlays/stats. Closing the last tab returns to the welcome page.
- `Open with` / `HANDLES_OPEN` reuses the active window and opens extra paths as tabs.
- Warm open: GLB prepare runs off the main thread in parallel with creating the new tab’s F3D engine; `scene.add` stays on the main thread. Closing mid-prepare must not leak retained temps (see [docs/MEMORY.md](docs/MEMORY.md)).

### 7. UI / theme / Preferences

- Color scheme defaults to **Follow System**; accent comes from the desktop portal (e.g. Ubuntu orange on Yaru).
- Header **theme** `MenuButton`: Follow System / Light / Dark (icons; `app.theme` stateful action). `Ctrl+,` or gear opens **Preferences** (`AdwPreferencesDialog`) for navigation, loading, HDRI/config folders, and save-settings.
- Custom CSS is limited to viewport chrome (floating header buttons, stats HUD, tab bar) — sidebar/lists stay Adwaita.
- Scene tab groups **Animation** + **Inspect** (see §4). Point sprites: `sphere` / `gaussian` / `circle` / `cross` / `stddev` / `bound`.

### 8. Viewport navigation

Blender-like controls with **classic Exhibit centering** as the default (model stays on the view center while orbiting). Full table, GSettings keys, and implementation notes: [`docs/NAVIGATION.md`](docs/NAVIGATION.md).

| Input | Action |
|-------|--------|
| Touchpad two-finger / LMB drag | Orbit (around **view center** by default) |
| Shift + drag / two-finger | Pan |
| Ctrl + drag / two-finger | Zoom |
| Scroll wheel (no touchpad orbit) | Zoom |
| **Alt** | Temporarily toggle cursor-pivot prefs (orbit/zoom under pointer ↔ view center) |
| Double-click LMB | Reset to bounds (frame model) |
| Middle-click (no drag) | Set orbit pivot under cursor (optional pref) |
| Header home | Same as reset to bounds |

Preferences → **Navigation** (or GSettings `nav-*` keys) for invert axes, sensitivities, touchpad orbit, zoom/orbit-to-cursor, middle-click pivot.

### 9. Preview performance & memory

- **Lazy** F3D engine create per tab (loading UI first). Reloads on the same tab reuse that engine; **closing** the tab destroys it (`scene.clear` + drop `engine` / animation timer).
- Cache prepared GLBs with LRU (see §1). Last `Viewer3dWindow` close also `clear_prepare_cache()`.
- Coalesce settings paints; part hide skips re-prepare when a prepared path is already available and loads the filtered GLB from memory.
- Idle auto-render off; animation tick ~60 Hz.
- Extra tabs skip auto-best preset churn (inherit current view settings).
- **Gotcha:** each open tab keeps its own F3D/VTK engine in RAM/GPU. Closing tabs should drop most RSS; a small residual after the first engine create is normal (allocator / GL). Details + how to measure: [docs/MEMORY.md](docs/MEMORY.md).

### 10. Flatpak / build changes

- Sandbox: `--filesystem=home`, `--filesystem=/tmp`, `--filesystem=/media` (symlink targets under `/media`), plus `xdg-config/gtk-3.0|4.0:ro` and Settings portal talk for OS theme/accent.
- **Stack:** F3D **v3.5.0** + VTK **9.6.2** in [`build-aux/libf3d.json`](build-aux/libf3d.json). Modules: EXR **ON**, WebP **ON**, ImGui UI **OFF**.
- **Patches:** depth linearize + normal-glyph world scale (`f3d-*.patch`); VTK cmake policies (`vtk-*.patch`).
- UI options mapped to F3D 3.5 enums (`blending.mode`, `antialiasing.mode`, `point_sprites.type`).
- **EGL:** do not rely on `create_external_egl()` under Flatpak — use `create_external(eglGetProcAddress)` after the tab `Gtk.GLArea` is realized (otherwise Loading… sticks). See [docs/RUNTIME.md](docs/RUNTIME.md#f3d-engine-init-wayland--flatpak).
- **Extra modules:** meshoptimizer, KTX-Software (`libktx`), **libwebp** (required for WebP — GNOME Sdk has no usable `WebPConfig.cmake`). Boost 1.91+: omit `system` from `--with-libraries` (header-only).
- Stabler fetches: skip F3D git-lfs blobs; ImageMagick from the GitHub mirror.
- Full pin table, WebP failure mode, same-filesystem `state-dir`, verify commands: **[docs/FLATPAK.md](docs/FLATPAK.md)**.

After changing Flatpak filesystem permissions or F3D patches, fully quit Exhibit (`flatpak kill io.github.nokse22.Exhibit`) before reopening — running instances keep the old sandbox / `/app`.

For other host paths:

```sh
flatpak run --filesystem=host io.github.nokse22.Exhibit render …
```

---

## Gamedev quick start

```sh
# Packed GLB (meshopt + quant ± BasisU), e.g. from gltfpack
gltfpack -c -i hero.gltf -o hero.glb

# Preview (after installing this fork as Flatpak)
flatpak run io.github.nokse22.Exhibit ./hero.glb
# or
flatpak run io.github.nokse22.Exhibit /tmp/hero.glb
```

- **Animations:** sidebar → Scene → **Active animation** (leave **None** for bind pose; see [docs/RUNTIME.md](docs/RUNTIME.md)).
- **Parts:** multipart `.glb` → list icon beside home/reset → tree checkboxes.
- **Inspect:** Scene → **Inspect** (armature, normals, depth, skin weights, stats) — see [docs/INSPECT_AND_PREPARE.md](docs/INSPECT_AND_PREPARE.md).
- **Tabs:** open a second GLB (dialog or drop) → new tab after the shared loading screen.
- **Orbit:** two-finger / LMB drag around view center; **Alt** for cursor orbit; **Preferences** (gear / `Ctrl+,`) for nav prefs — see [`docs/NAVIGATION.md`](docs/NAVIGATION.md).
- **Compare:** `Ctrl+Shift+C` sync cameras; `Ctrl+Shift+D` Split Compare; pin + `Ctrl+Shift+X` swap — [`docs/SPLIT_COMPARE.md`](docs/SPLIT_COMPARE.md).
- **Batch views:** `exhibit render` (see above).
- **Fork notes index:** [`docs/README.md`](docs/README.md).

---

## Tests

~1300 unit/pipeline tests (prepare, pack, stats, camera, CLI parser, session restore, mixin helpers). Default suite needs **no Gtk/F3D**:

```sh
python3 -m pip install pytest   # once
./tools/run_tests.sh
# or: python3 -m pytest tests/
```

- Full guide (layout, factories, CLI `--up=-Y` quirk): **[docs/TESTING.md](docs/TESTING.md)**
- Docs index: **[docs/README.md](docs/README.md)**
- Session restore anti-regression: `tests/test_session_restore_queue.py` — see [docs/SESSION_RESTORE.md](docs/SESSION_RESTORE.md)
- Tab / F3D RSS (Flatpak + display): `tools/profile_tab_memory.py` — see [docs/MEMORY.md](docs/MEMORY.md)
- CI: [`.github/workflows/pytest.yml`](.github/workflows/pytest.yml)

```sh
EXHIBIT_MESH_DIR=/path/to/big/glbs EXHIBIT_PROFILE_FILES=3 \
flatpak run --filesystem=host --command=python3 io.github.nokse22.Exhibit \
  "$(pwd)/tools/profile_tab_memory.py"
```

---

## Build (Flatpak, local)

Needs `org.flatpak.Builder`, GNOME 50 SDK/Platform, and Flathub remotes.

```sh
git clone https://github.com/maikramer/Exhibit.git
cd Exhibit

mkdir -p "$HOME/exhibit-fp-state" "$HOME/exhibit-fp-repo" "$HOME/exhibit-fp-build"

flatpak run org.flatpak.Builder \
  --force-clean \
  --user \
  --install \
  --ccache \
  --state-dir="$HOME/exhibit-fp-state" \
  --repo="$HOME/exhibit-fp-repo" \
  "$HOME/exhibit-fp-build" \
  build-aux/io.github.nokse22.Exhibit.json
```

Then:

```sh
flatpak run io.github.nokse22.Exhibit path/to/model.glb
```

GNOME Builder against this repo also works if you prefer an IDE workflow.

Build notes (pins, WebP/libwebp, `state-dir`, patches): [docs/FLATPAK.md](docs/FLATPAK.md).

---

## Docs

Index of topic guides: [docs/README.md](docs/README.md).

---

## License

Exhibit (including this fork) is **GPLv3**. F3D is under the **3-Clause BSD License**; see [F3D licensing](https://github.com/f3d-app/f3d?tab=readme-ov-file#license) for dependent libraries. Meshoptimizer, KTX-Software, and libwebp ship under their own licenses as bundled Flatpak modules.
