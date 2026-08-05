# Flatpak build notes

Local install recipe: [README → Build](../README.md#build-flatpak-local).
Manifest: [`build-aux/io.github.nokse22.Exhibit.json`](../build-aux/io.github.nokse22.Exhibit.json)
→ F3D stack in [`build-aux/libf3d.json`](../build-aux/libf3d.json).

---

## Current pin (fork)

| Component | Version / note |
|-----------|----------------|
| Runtime / SDK | **org.gnome.Platform/Sdk //50** (Flathub stable; CI image `gnome-50`) |
| F3D | **v3.5.0** (`bcfa8d525cec…`), `disable-lfs` |
| VTK | **9.6.2** |
| Modules | EXR **ON**, WebP **ON**, ImGui UI **OFF** |
| Extra libs | meshoptimizer, libktx, **libwebp 1.6.0** |
| F3D patches | `f3d-linearize-display-depth.patch`, `f3d-normal-glyphs-scale.patch` |
| VTK patches | `vtk-cmake-policies-0174-0177.patch`, `vtk-vtktiff-cmake-policy-3.10.patch` |

Majors also bumped in-tree: Boost 1.91, Eigen 3.4.1, oneTBB 2022.3, assimp 6.0.5, OpenUSD v25.11, OpenSubdiv 3.7, OCCT V7_9_x, GLEW 2.3.1, ImageMagick 6.9.13-x, pybind11 3.0.4, …

---

## Learnings

### `F3D_MODULE_WEBP=ON` needs a libwebp module

GNOME Sdk does **not** ship a CMake `WebPConfig.cmake` that F3D’s `find_package(WebP)` accepts.
Turning WebP on without bundling libwebp fails at F3D configure time.

Ship **libwebp** as a Flatpak module before F3D (see `libf3d.json`). Keep tools off
(`WEBP_BUILD_CWEBP=OFF`, …) — only the shared library is required.

### Keep `F3D_MODULE_UI=OFF`

ImGui `ui.scene_hierarchy` would fight the Gtk **outliner overlay** on the
embedded `GLArea` ([OUTLINER.md](OUTLINER.md)). Part hide stays: filter GLB →
`scene.add(bytes)` ([INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md)).

### State dir and build dir on the same filesystem

`flatpak-builder` warns / misbehaves when `--state-dir` and the app build dir sit on
different mounts (e.g. repo on external disk, state on `$HOME`). Put both under
`$HOME/exhibit-fp-*` as in the README.

### Skip F3D git-lfs

F3D’s test assets are huge LFS blobs. Manifest sets `"disable-lfs": true` on the
F3D git source so local/CI builds stay usable.

### VTK policy patches

VTK 9.6 + newer CMake need CMP0174/0177 and vtktiff policy bumps — see
`build-aux/patches/vtk-*.patch`. Prefer real patches over `-Wno-dev` / disabling features.

### Boost 1.91+ — do not build `system`

`Boost.System` is header-only. Passing `--with-libraries=…,system` makes
`bootstrap` fail (`wrong library name 'system'`). Keep
`iostreams,filesystem,date_time,regex,program_options,python` only
(`build-aux/libf3d.json`).

### App-only rebuild (fast)

Empty `$HOME/exhibit-fp-build` and rebuild **without** wiping `--state-dir` so
VTK/OCCT/etc. stay cached (~1–2 min for the `exhibit` module). Use
`--force-clean` only when F3D/VTK/patches or Boost change.

### After permission or patch changes

```sh
flatpak kill io.github.nokse22.Exhibit
# rebuild with --force-clean when F3D/VTK/patches change
```

Running instances keep the old sandbox and old `/app` libs.

Runtime EGL / Loading… stuck: [RUNTIME.md](RUNTIME.md#f3d-engine-init-wayland--flatpak).

### Host paths outside the sandbox

```sh
flatpak run --filesystem=host io.github.nokse22.Exhibit render …
```

Sandbox defaults: `$HOME`, `/tmp`, `/media`, gtk config ro, Settings portal.
`ffmpeg` for `--video` uses `flatpak-spawn --host` when missing inside the sandbox.

---

## Verify install

```sh
flatpak run --command=f3d io.github.nokse22.Exhibit --version
# expect: F3D 3.5.0, Module WebP: ON, Module OpenEXR: ON, Module ImGui: OFF
```
