<img height="128" src="data/icons/hicolor/scalable/apps/io.github.nokse22.Exhibit.svg" align="left"/>

# Exhibit (fork)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![made-with-python](https://img.shields.io/badge/Made%20with-Python-ff7b3f.svg)](https://www.python.org/)

Fork of **Exhibit** for a **gamedev asset workflow**: open packed GLBs from gltfpack-style pipelines, flip animation clips, hide mesh parts, inspect armatures/stats, and batch-render views for AI review — without leaving the desktop.

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
| **GLB prepare** | Expand meshopt + mesh quantization; transcode KTX2/BasisU → PNG before F3D/VTK load |
| **Animation** | Clip names in a combo; switch clip without full model reload |
| **Parts** | Floating object tree to hide/show glTF mesh nodes |
| **Armature** | X-ray skeleton overlay (thicker bones + translucent mesh) |
| **Stats** | Vertex/face/edge/height overlay in the GUI; same counts in CLI PNGs + `manifest.json` |
| **Tabs** | Multi-document `AdwTabView`: each open/drop adds a tab; shared sidebar; same startup loading UI |
| **Compare** | **Sync Cameras** + experimental **Split Compare** (side-by-side column, Pin, Swap; shortcuts below) |
| **Recent** | Welcome page lists recent models (GSettings); drop a folder to open all GLB/glTF |
| **Session** | Optionally restore last open tabs on startup (Loading → **Restore Last Session**) |
| **UI** | Follow OS theme/accent (Yaru/Adwaita portal); Scene-tab IA (Animation + Inspect); glass chrome over the viewport |
| **CLI** | `exhibit render` → multi-angle PNGs + optional turntable `--video` + `manifest.json` |
| **Perf** | Cached prepare (LRU count + 256 MiB); warm second-open (prepare ∥ new F3D engine); ~60 Hz anim tick |
| **Flatpak** | `$HOME` + `/tmp` + `/media`; gtk config + Settings portal; pinned F3D; `libmeshoptimizer` + `libktx`; host `ffmpeg` via `flatpak-spawn` |

### 1. Packed GLB preparation (before F3D load)

F3D/VTK/Assimp cannot load several common packed-glTF extensions. On `.glb` open (GUI and CLI), the fork rewrites a temporary file when needed:

1. **`EXT_meshopt_compression` / `KHR_meshopt_compression`** — decode with `libmeshoptimizer` (filters: NONE, OCTAHEDRAL, QUATERNION, EXPONENTIAL, COLOR). Destination buffers are padded to a multiple of 4 so meshopt filters do not overrun (gltfpack LOD meshes).
2. **`KHR_mesh_quantization`** — expand quantized `POSITION` / `NORMAL` / `TANGENT` / `TEXCOORD_*` accessors to float and strip the extension.
3. **`KHR_texture_basisu` (KTX2 / BasisU)** — via `libktx`:
   - if the texture already has a PNG/JPEG `source` fallback → keep it and drop the BasisU extension;
   - otherwise decode the KTX2 image to PNG, rewrite the GLB, and strip `KHR_texture_basisu` from `extensionsUsed` / `extensionsRequired`.

Prepared temps are **cached** by `(realpath, mtime, size)` so reopen / part-toggle / CLI batches do not re-decode the same file every time.

Self-contained `.glb` and external `.gltf` + URI buffers/images (local or `data:`) are supported. Remote `http(s)` URIs are not.

### 2. Animation clips by name

- Sidebar → Scene → **Active animation** is an `AdwComboRow` fed by F3D `get_animation_names` (plus **None** and **All animations**).
- Default is **None** (empty `scene.animation.indices`) so the mesh stays in bind/rest pose until a clip is selected.
- Changing the clip updates `scene.animation.indices` and scrubber bounds **in place** — no full reload.

### 3. Object tree (multipart visibility)

- Header **list** button (next to home/reset) opens a popover with the glTF node hierarchy.
- Checkboxes hide/show mesh parts. The scene is rewritten with hidden nodes filtered out, then reloaded while **preserving camera and animation time**.
- Demo asset: [Cesium Milk Truck](https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/CesiumMilkTruck) (GLB).

### 4. Armature X-ray

- View → **Armature** switch: enable F3D armature, raise edge line width, lower mesh opacity so the skeleton reads as an X-ray overlay.
- Toast if the model has no glTF skins.
- CLI: `--armature` (defaults opacity `0.35`, line width `4` unless overridden).

### 5. Mesh stats

- View → **Show Stats**: Gtk overlay with height (meters, glTF / Three.js +Y AABB), verts / faces / edges, and related counts.
- CLI: stats always land in `manifest.json` under `stats` (includes `height_m`); `--overlay` also burns them into the PNGs via F3D’s text overlay.
- Counts come from the prepared GLB when prepare ran (so meshopt/quantized assets report post-expand geometry). Height is **lazy** (computed on first overlay/manifest use) from POSITION `min`/`max` + node world matrices — same idea as Three.js `Box3.setFromObject`; no vertex-buffer scan.

### 6. Headless CLI render (`exhibit render`)

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
| `--up` | `+Y` (default), `-Y`, `+Z`, … |
| `--armature` | Skeleton X-ray defaults |
| `--opacity` / `--line-width` | Override mesh opacity / edge width |
| `--edges` | Show mesh edges |
| `--grid` / `--no-grid` | Ground grid (default off) |
| `--bg R,G,B` | Background 0..1 (default `0.12,0.12,0.12`) |
| `--animation-index` / `--animation-time` | Clip index + time in seconds |
| `--overlay` | Burn mesh stats into PNGs |
| `--format png` | Only PNG for now |
| `--video mp4\|webm\|gif` | Turntable video (`ffmpeg` for mp4/webm; Pillow GIF; auto-GIF if ffmpeg missing). Flatpak: uses host `ffmpeg` via `flatpak-spawn --host` when sandbox PATH has none |
| `--video-fps N` | Turntable frame rate (default `24`) |

Manifest includes model path, whether prepare ran, skins/animation names, `stats`, options used, view files, and optional `video` filename.

### 7. Multi-document tabs

- Opening or dropping another model while one is already loaded creates a **new tab** (file dialog supports multi-select).
- Drop a **folder** (or multiple files), or use **Open Folder** (`Ctrl+Shift+O`), to open every supported GLB/glTF in new tabs.
- Welcome page shows **Recent** models (persisted in GSettings), with **Clear Recent**.
- **Restore Last Session** (sidebar Loading, default on) reopens the previous tabs on startup unless a file is passed on the command line; turn off to clear saved session paths.
- Settings menu → **Sync Cameras Across Tabs** keeps peer-tab cameras matched while you navigate.
- **Split Compare (Experimental)** checklist:
  - `Ctrl+Shift+D` — toggle side-by-side secondary F3D column (drag sash to resize; width remembered)
  - **Pin secondary model** — keep another file while switching tabs (camera still follows the active tab; pin path restored on next launch if the file exists)
  - `Ctrl+Shift+X` — **Swap** active tab ↔ pinned model
  - Split Compare + pin reopen quietly on the next launch when left on
- First file: no tab bar. Second file: same startup **Loading…** page, then the model appears and the tab bar reveals with both documents.
- Sidebar settings apply across tabs; animation scrubber / object tree follow the **active** tab.
- Closing the last tab returns to the welcome page. `Open with` / `HANDLES_OPEN` reuses the active window and opens extra paths as tabs.
- Warm open (app already running): GLB prepare runs in parallel with creating the new tab’s F3D engine; `scene.add` stays on the main thread.

### 8. UI / theme

- Color scheme defaults to **Follow System**; accent comes from the desktop portal (e.g. Ubuntu orange on Yaru).
- Custom CSS is limited to viewport chrome (floating header buttons, stats HUD, tab bar) — sidebar/lists stay Adwaita.
- Scene tab groups **Animation** + **Inspect** (armature, stats). Startup copy targets packed-GLB / gamedev preview.

### 9. Preview performance

- Reuse the F3D engine across loads when possible; **lazy** engine create per new tab (loading UI first).
- Cache prepared GLBs (see §1).
- Coalesce settings paints instead of applying one-by-one.
- Part hide avoids a full meshopt/KTX re-decode when a prepared path is already available.
- Idle auto-render off; animation tick ~60 Hz.
- Extra tabs skip auto-best preset churn (inherit current view settings).

### 10. Flatpak / build changes

- Sandbox: `--filesystem=home`, `--filesystem=/tmp`, `--filesystem=/media` (symlink targets under `/media`), plus `xdg-config/gtk-3.0|4.0:ro` and Settings portal talk for OS theme/accent.
- **F3D pin:** commit `302c6f00695666ca090389ab8ed212283213faa9` in [`build-aux/libf3d.json`](build-aux/libf3d.json); UI options mapped to current F3D enums (`blending.mode`, `antialiasing.mode`, `point_sprites.type`).
- Extra modules: **meshoptimizer**, **KTX-Software (`libktx`)**.
- Stabler fetches: skip F3D git-lfs blobs; ImageMagick from the GitHub mirror.

After changing Flatpak filesystem permissions, fully quit Exhibit (`flatpak kill io.github.nokse22.Exhibit`) before reopening — running instances keep the old sandbox.

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

- **Animations:** sidebar → Scene → **Active animation**.
- **Parts:** multipart `.glb` → list icon beside home/reset → tree checkboxes.
- **Armature / stats:** Scene → **Show Armature** / **Show Stats**.
- **Tabs:** open a second GLB (dialog or drop) → new tab after the shared loading screen.
- **Batch views:** `exhibit render` (see above).

---

## Tests (host, no Flatpak)

Pipeline unit tests (GLB prepare, glTF pack, stats, camera, CLI parser) run without Gtk/F3D:

```sh
python3 -m pytest tests/
# or
./tools/run_tests.sh
```

CI: `.github/workflows/pytest.yml`.

---

## Build (Flatpak, local)

Needs `org.flatpak.Builder`, GNOME 49 SDK/Platform, and Flathub remotes.

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

### Unit tests (host, no Flatpak / Gtk)

Pipeline helpers (prepare, pack `.gltf`, stats, camera, CLI parser) run with pytest:

```sh
python3 -m pip install pytest   # once
./tools/run_tests.sh
# or: python3 -m pytest tests/
```

CI: `.github/workflows/pytest.yml`.

---

## License

Exhibit (including this fork) is **GPLv3**. F3D is under the **3-Clause BSD License**; see [F3D licensing](https://github.com/f3d-app/f3d?tab=readme-ov-file#license) for dependent libraries. Meshoptimizer and KTX-Software ship under their own licenses as bundled Flatpak modules.
