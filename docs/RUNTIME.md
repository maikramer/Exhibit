# Runtime learnings (Flatpak / F3D / animation)

Durable gotchas from shipping the gamedev fork under Flatpak + F3D 3.5.
Companion to [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md) (asset pipeline) and
[SESSION_RESTORE.md](SESSION_RESTORE.md) (tab queue / GL realize).

---

## F3D engine init (Wayland / Flatpak)

### Symptom

Opening any model → **Loading… forever**. Log:

```text
Initializing F3D with EGL
RuntimeError: Cannot find EGL library
```

Uncaught exception in warm-load left the spinner up (fixed: surface error / never leave loading forever).

### Cause

`f3d.Engine.create_external_egl()` often fails inside Flatpak even when
`libEGL.so.1` is present (`ctypes.CDLL("libEGL.so.1")` works;
`get_rendering_backend_list()` may still report all backends `False`).

### Fix (current code)

1. Wait until the tab’s `Gtk.GLArea` is **realized**.
2. `make_current()`.
3. Prefer `f3d.Engine.create_external(eglGetProcAddress)` (or GLX
   `glXGetProcAddress*` on X11), then fall back to `create_external_egl` /
   `create_external_glx`.

Code: `src/widgets/f3d_viewer.py` (`_gl_get_proc_address`, `initialize`).

### Warm-load UI constraint

Full-page startup **Loading…** used to unmap the 3d page → GLArea never
realized → init impossible. Load keeps **`3d_page` mapped** and selects the
target tab so the GLArea can map while prepare runs off-main.

`scene.add` stays on the main thread. See also [SESSION_RESTORE.md](SESSION_RESTORE.md)
(why batch opens must be sequential).

---

## Animation: None = bind pose

### User-facing

| Combo entry | Setting `animation-index` | F3D `scene.animation.indices` |
|-------------|---------------------------|--------------------------------|
| **None** (default) | `None` | empty |
| **All animations** | `-1` | `[-1]` (all) |
| Clip name | `0…N-1` | `[i]` |

- Fresh open resets to **None** (reload / preserve-orientation keeps the clip).
- Play + scrubber disabled while None.
- Selecting a clip updates indices **in place** (no full reload) and jumps to
  the clip’s lower time.

### Selecting None again must reimport

Clearing indices alone **does not** restore bind/rest pose — VTK/F3D leaves the
last skin pose on the actors. F3D’s own cycle (`W`) eventually reloads at
time-range start after disabling clips; empty indices make `LoadAtTime` a no-op.

Exhibit calls `F3DViewer.reset_to_bind_pose()` → clear + `scene.add` of the
prepared path with empty indices, **camera preserved** (same path as part
visibility reload).

Code: `window_animation.py` (`on_animation_combo_changed`),
`f3d_viewer_load.py` (`reset_to_bind_pose`).

### Python bindings quirk

`options.update({"scene.animation.indices": []})` → `TypeError`.
Empty vector is set with **`""`** (string), which clears to `[]`.

Mapped in `_map_setting_to_f3d` when `animation-index is None`.

---

## Dense meshes (voxel / MC intermediates)

Assets like VibeGame `_intermediate/*_shape.glb` are often **1–8M verts**,
no textures, no meshopt — prepare is a no-op; F3D load is fine.

Exact unique-edge stats build a Python `set` of all triangle edges → multi-second
main-thread stalls. Above **750 000** indices, stats use the approximate
`faces × 1.5` estimate (`mesh_stats.py`).

---

## External file changes

`FileWatchMixin` polls every loaded tab’s mtime:

| Mode | Active tab | Background tabs |
|------|------------|-----------------|
| **Reload On Change** on | silent reload (preserve camera) | mark `(modified)` + prompt on select |
| off | prompt Reload / Keep | mark + prompt on select |

Never title a tab `"Nothing"` — fallback `Untitled`; modified suffix is
`name.glb (modified)`.

Code: `window_file_watch.py`, `viewer_tab.py` (`externally_modified`).

---

## See also

- Build pins / Boost / fast rebuild: [FLATPAK.md](FLATPAK.md)
- Prepare + Inspect overlays: [INSPECT_AND_PREPARE.md](INSPECT_AND_PREPARE.md)
- Session queue / GL realize: [SESSION_RESTORE.md](SESSION_RESTORE.md)
