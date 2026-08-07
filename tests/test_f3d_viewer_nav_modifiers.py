# SPDX-License-Identifier: GPL-3.0-or-later
"""Nav wiring checks for libexhibit migration (Exb.View + gschema)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW_C = ROOT / "libexhibit" / "exb-view.c"
GSCHEMA = ROOT / "data" / "io.github.nokse22.Exhibit.gschema.xml"
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"


def test_exb_view_has_orbit_pan_zoom_gestures():
    src = VIEW_C.read_text(encoding="utf-8")
    eng = (ROOT / "libexhibit" / "exb-engine.c").read_text(encoding="utf-8")
    assert "gtk_gesture_drag_new" in src
    assert "exb_engine_rotate" in src
    assert "exb_engine_pan" in src
    assert "exb_engine_zoom" in src
    assert "gtk_event_controller_scroll_new" in src
    assert "GTK_EVENT_CONTROLLER_SCROLL_BOTH_AXES" in src
    assert "invert-x" in src
    assert "orbit-sensitivity" in src
    assert "GDK_SHIFT_MASK" in src
    assert "GDK_CONTROL_MASK" in src
    assert "GDK_ALT_MASK" in src
    assert "zoom-to-cursor" in src
    assert "orbit-around-cursor" in src
    assert "touchpad-orbit" in src
    assert "mmb-click-pivot" in src
    assert "free-navigation" in src
    assert "gtk_gesture_click_new" in src
    assert "_exb_engine_zoom_at_ndc" in eng
    assert "_exb_engine_pivot_at_ndc" in eng


def test_pinch_uses_scale_ratio_not_delta():
    """Pinch must pass scale/prev_scale — raw deltas collapse the camera."""
    src = VIEW_C.read_text(encoding="utf-8")
    body = src.split("on_zoom_changed", 1)[1].split("on_drag_begin", 1)[0]
    assert "scale / priv->prev_scale" in body
    assert "(scale - priv->prev_scale)" not in body
    assert "exb_view_clamp_dolly_factor" in body
    eng = (ROOT / "libexhibit" / "exb-engine.c").read_text(encoding="utf-8")
    zoom = eng.split("exb_engine_zoom (", 1)[1].split("exb_engine_pan (", 1)[0]
    assert "CLAMP (factor, 0.5, 2.0)" in zoom


def test_free_navigation_ctrl_shift_shortcuts():
    src = VIEW_C.read_text(encoding="utf-8")
    assert "free_navigation && ctrl && shift" in src
    assert "free_pan" in src


def test_shim_wires_touchpad_and_mmb_prefs():
    src = VIEWER.read_text(encoding="utf-8")
    assert '"nav-touchpad-orbit": "touchpad-orbit"' in src
    assert '"nav-mmb-click-pivot": "mmb-click-pivot"' in src
    assert '"nav-free-navigation": "free-navigation"' in src


def test_shim_stores_nav_settings():
    src = VIEWER.read_text(encoding="utf-8")
    assert "def apply_nav_settings" in src
    assert "_nav_settings" in src


def test_gschema_keeps_fork_nav_keys():
    src = GSCHEMA.read_text(encoding="utf-8")
    for key in (
        "nav-invert-x",
        "nav-invert-y",
        "nav-zoom-to-cursor",
        "nav-orbit-around-cursor",
        "nav-touchpad-orbit",
        "nav-mmb-click-pivot",
        "nav-free-navigation",
        "nav-show-cube",
    ):
        assert f'name="{key}"' in src


def test_orbit_around_cursor_default_is_off():
    src = GSCHEMA.read_text(encoding="utf-8")
    # Key block contains default false for orbit-around-cursor
    idx = src.index('name="nav-orbit-around-cursor"')
    chunk = src[idx : idx + 200]
    assert "<default>false</default>" in chunk
