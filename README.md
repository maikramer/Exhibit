<img height="128" src="data/icons/hicolor/scalable/apps/io.github.nokse22.Exhibit.svg" align="left"/>

# Exhibit (fork)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![made-with-python](https://img.shields.io/badge/Made%20with-Python-ff7b3f.svg)](https://www.python.org/)

Fork of **Exhibit** tuned for a **gamedev asset workflow**: preview packed GLBs, flip animation clips, and toggle mesh parts without leaving the desktop.

Powered by [F3D](https://github.com/f3d-app/f3d) (glTF, USD, STL, FBX, OBJ, PLY, and more).

<br clear="left"/>

## Credits

- **Original app:** [Nokse22/Exhibit](https://github.com/Nokse22/Exhibit) by [Nokse](https://github.com/Nokse22) — GPLv3.
- **Renderer:** [F3D](https://github.com/f3d-app/f3d) — BSD-3-Clause (see F3D license notes for bundled libs).
- **This fork:** [maikramer/Exhibit](https://github.com/maikramer/Exhibit) — gamedev-focused changes on top of upstream.

Upstream Flathub build (original app, not this fork):  
https://flathub.org/apps/io.github.nokse22.Exhibit

## Why this fork

Upstream Exhibit is a great GNOME viewer. This fork adds what a game pipeline needs when assets come from **gltfpack** / mesh pipelines:

| Feature | What it does |
|--------|----------------|
| **Meshopt + quantization** | Decompress `EXT`/`KHR_meshopt_compression` and expand `KHR_mesh_quantization` before F3D/VTK load |
| **Animation by name** | Sidebar combo lists clip names; switch without full reload |
| **Object tree** | Header popover (next to home/reset) shows glTF hierarchy; hide/show mesh parts |
| **Flatpak local paths** | Sandbox can read `$HOME` and `/tmp` for CLI/drop loads |

App ID stays `io.github.nokse22.Exhibit` so local Flatpak/GSettings stay compatible with upstream installs.

## Gamedev quick start

```sh
# Packed GLB (meshopt + quant), e.g. from gltfpack
gltfpack -c -i hero.gltf -o hero.glb

# Preview (after installing this fork as Flatpak)
flatpak run io.github.nokse22.Exhibit ./hero.glb
# or
flatpak run io.github.nokse22.Exhibit /tmp/hero.glb
```

- **Animations:** open sidebar → Scene → **Active animation**.
- **Parts:** with a multipart `.glb`, click the **list** icon beside home/reset → checkboxes on the tree.
- **Multipart demo:** [Cesium Milk Truck](https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/CesiumMilkTruck) (GLB).

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

## Roadmap (fork)

- Reliable preview of **meshopt / quantized** GLBs from pack tools  
- Fast **animation clip** iteration by name  
- **Part visibility** for multipart characters/props  
- Further gamedev conveniences as the pipeline needs them  

## License

Exhibit (including this fork) is **GPLv3**. F3D is under the **3-Clause BSD License**; see [F3D licensing](https://github.com/f3d-app/f3d?tab=readme-ov-file#license) for dependent libraries.
