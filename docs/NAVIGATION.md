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
| **Alt** (hold) | Temporarily XOR-toggle cursor-orbit / zoom-to-cursor prefs |
| Double-click LMB | Reset to bounds |
| Middle-click (no drag) | Set orbit pivot under cursor (if pref on) |
| Header home | Reset to bounds |

---

## Classic vs cursor pivot

| Mode | When | Pivot |
|------|------|-------|
| **Classic** (default) | `nav-orbit-around-cursor=false` | Focal / view center — model stays framed |
| **Cursor** | pref on, or **Alt** while classic | World point under pointer on focal plane |

Zoom-to-cursor (`nav-zoom-to-cursor`, default on) is independent of orbit mode.
Existing user GSettings may still have old `nav-orbit-around-cursor=true` until reset.

---

## GSettings (`nav-*`)

Defaults mirror `NAV_SETTING_DEFAULTS` in `src/camera_nav.py`.

| Key | Default | Meaning |
|-----|---------|---------|
| `nav-invert-x` | `false` | Flip horizontal orbit/pan |
| `nav-invert-y` | `false` | Flip vertical orbit/pan/zoom-drag |
| `nav-zoom-to-cursor` | `true` | Zoom toward pointer (not view center) |
| `nav-orbit-around-cursor` | `false` | Orbit under pointer on focal plane; off = classic center |
| `nav-touchpad-orbit` | `true` | Two-finger scroll orbits; else zooms like mouse wheel |
| `nav-mmb-click-pivot` | `true` | MMB click (no drag) recenters orbit target |
| `nav-orbit-sensitivity` | `1.0` | Orbit multiplier (0.25–4.0) |
| `nav-zoom-sensitivity` | `1.0` | Zoom multiplier (0.25–4.0) |
| `nav-pan-sensitivity` | `1.0` | Pan multiplier (0.25–4.0) |

---

## Code

| File | Role |
|------|------|
| `src/camera_nav.py` | Math helpers + defaults |
| `src/widgets/f3d_viewer.py` | Shim: `apply_nav_settings` → `Exb.View` props |
| `libexhibit/exb-view.c` | Gestures (drag/scroll/click); touchpad-orbit, MMB pivot, double-click reset |
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

### Scroll / dolly safety
- Clamp scroll deltas and dolly factors; reject insane pivots (`is_sane_pivot`).
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
- Sidebar “More” tab removed; settings live in `AdwPreferencesDialog`.
- Header: theme `GtkMenuButton` + preferences gear (`PreferencesMixin`).
