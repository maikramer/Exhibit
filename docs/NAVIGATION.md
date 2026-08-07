# Viewport navigation

Blender-like orbit/pan/zoom with **classic Exhibit centering** by default
(model stays on the view/focal center while orbiting).

UI summary: [README §8b](../README.md#8b-viewport-navigation).
Prefs: **Preferences → Navigation** (`Ctrl+,` / gear) or GSettings `nav-*`.
Window glue: [ARCHITECTURE.md](ARCHITECTURE.md) (`PreferencesMixin`, `LifecycleMixin` home).

---

## Inputs

| Input | Action |
|-------|--------|
| Touchpad two-finger / LMB drag | Orbit |
| Shift + drag / two-finger | Pan |
| Ctrl + drag / two-finger | Zoom |
| Scroll wheel (when touchpad-orbit off) | Zoom |
| Pinch (two-finger scale) | Zoom (factor = scale ratio, clamped) |
| **Ctrl+Shift+drag** (free-nav on) | Pan |
| **Ctrl+Shift+scroll** (free-nav on) | Zoom (even with touchpad-orbit) |
| **Alt** (hold) | Temporarily XOR-toggle cursor-orbit / zoom-to-cursor prefs |
| Double-click LMB | Reset to bounds |
| Middle-click (no drag) | Set orbit pivot under cursor (if pref on) |
| Header home | Reset to bounds |
| Navigation cube (face click) | Jump to front/back/left/right/top/bottom |

---

## Classic vs cursor pivot

| Mode | When | Pivot |
|------|------|-------|
| **Classic** (default) | `nav-orbit-around-cursor=false` | Focal / view center — model stays framed |
| **Cursor** | pref on, or **Alt** while classic | World point under pointer on focal plane |

Zoom-to-cursor (`nav-zoom-to-cursor`, default on) is independent of orbit mode.
Existing user GSettings may still have old `nav-orbit-around-cursor=true` until reset.

---

## Free navigation

When `nav-free-navigation` is on (More → Navigation), **Ctrl+Shift** shortcuts are
added on top of the usual Shift/Ctrl modifiers:

- Ctrl+Shift+LMB drag → pan
- Ctrl+Shift+scroll → zoom (always zoom, not orbit)

---

## Navigation cube

Overlay in the top-right of each tab (`src/widgets/nav_cube.py`). Orientation
tracks the camera; click a face for a named view. Toggle with `nav-show-cube`.

**Fly** icon (airplane) under the cube: FPS free-fly. Turning it on snapshots the camera,
disables orbit gestures, then:

| Input | Action |
|-------|--------|
| Click view | Toggle mouse-look (1st enter, 2nd release) |
| Mouse move (look on) | Look (low sens + short coast) |
| Esc | Release mouse-look |
| W / S | Forward / back (accel + drag) |
| A / D | Strafe left / right (accel + drag) |
| Shift + W / S | Up / down (world up) |

Turning Fly off restores the snapshotted view and normal orbit navigation.
(More → Free Navigation Ctrl+Shift shortcuts are separate.)

---

## GSettings (`nav-*`)

Defaults mirror `NAV_SETTING_DEFAULTS` in `src/camera_nav.py`.

| Key | Default | Meaning |
|-----|---------|---------|
| `nav-invert-x` | `false` | Flip horizontal orbit/pan |
| `nav-invert-y` | `false` | Flip vertical orbit/pan/zoom-drag |
| `nav-zoom-to-cursor` | `true` | Zoom toward pointer (not view center) |
| `nav-orbit-around-cursor` | `false` | Orbit under pointer on focal plane; off = classic center |
| `nav-touchpad-orbit` | `true` | Two-finger scroll orbits; else zooms like a mouse wheel |
| `nav-mmb-click-pivot` | `true` | MMB click (no drag) recenters orbit target |
| `nav-free-navigation` | `false` | Enable Ctrl+Shift pan/zoom shortcuts |
| `nav-show-cube` | `true` | Show navigation cube overlay |
| `nav-orbit-sensitivity` | `1.0` | Orbit multiplier (0.25–4.0) |
| `nav-zoom-sensitivity` | `1.0` | Zoom multiplier (0.25–4.0) |
| `nav-pan-sensitivity` | `1.0` | Pan multiplier (0.25–4.0) |

---

## Code

| File | Role |
|------|------|
| `src/camera_nav.py` | Math helpers + defaults |
| `src/widgets/f3d_viewer.py` | Shim: `apply_nav_settings` → `Exb.View` props |
| `src/widgets/nav_cube.py` | Clickable view cube overlay |
| `libexhibit/exb-view.c` | Gestures (drag/scroll/pinch/click); free-nav modifiers |
| `libexhibit/exb-engine.c` | Zoom/pan/rotate + dolly factor clamp |
| `src/window_preferences.py` | PreferencesMixin / dialog / theme menu |
| `src/window_lifecycle.py` | Header home → `reset_to_bounds` |
| `data/io.github.nokse22.Exhibit.gschema.xml` | `nav-*` keys |
| `tests/test_camera_nav.py` | Unit coverage for helpers |
| `tests/test_f3d_viewer_nav_modifiers.py` | Exb.View gesture / gschema wiring |
| `tests/test_window_preferences.py` | Prefs mixin |
| `tests/test_camera_views*.py`, `test_camera_orbit_grid.py` | Preset / orbit matrices — [TESTING.md](TESTING.md) |

---

## Implementation notes (learnings)

### Orbit / pole
- Cursor pivots use F3D `get_world_from_display` / `get_display_from_world`.
- Near poles (`view ∥ up`), `elevation_axis()` must fall back — hard-gating orbit
  with `_elevation_gimbal_allows` **froze** the camera at the top.
- Soft fix: `clamp_camera_polar(..., min_polar_deg=2)` after orbit; keep orbit
  path always available.

### Scroll / dolly / pinch safety
- Clamp scroll deltas and dolly factors (0.5…2.0) in C (`exb_engine_zoom`) and
  Python (`clamp_dolly_factor`); reject insane pivots (`is_sane_pivot`).
- Pinch must pass a **ratio** (`scale / prev_scale`), not a raw delta — deltas near
  0 collapsed the camera (scene “disappears”).
- Disable GTK kinetic scrolling on the viewer — fling made models “disappear”.

### Classic centering
- Default orbit around **focal**, not pointer, so the asset does not drift off-screen.
- **Alt** XOR-toggles effective cursor-orbit / zoom-to-cursor for that gesture only
  (not written back to GSettings).

### GTK / PyGObject pitfalls
- `@Gtk.Template.Callback` on mixins can become a non-callable **`CallThing`** —
  do **not** pass those handlers to `Gio.SimpleAction.connect`.
- Header chrome under paned (home, preferences, theme): prefer `widget.connect(...)`
  or `action-name` over Template.Callback from UI XML.
- Tab close: wire `tab_view.connect("close-page", ...)` in Python, not only UI signal.
- Theme icons: use existing Adwaita names
  (`preferences-desktop-appearance-symbolic`, `display-brightness-symbolic`,
  `weather-clear-night-symbolic`). **`dark-mode-symbolic` does not exist** → red square.
- Theme menu: build `Gio.Menu` in Python; fragile XML icon/target attrs broke easily.
- Do not `pkill -f` patterns that match the shell command line itself when killing
  the app during smoke tests.

### Preferences UI
- Navigation prefs live in sidebar **More** (`PreferencesMixin.on_preferences_clicked`).
- Free Navigation + Navigation Cube switches are wired via `WindowSettings`.
