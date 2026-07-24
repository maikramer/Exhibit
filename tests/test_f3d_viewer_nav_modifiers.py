# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for Alt / double-click navigation wiring."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"
VIEWER_UI = ROOT / "data" / "ui" / "f3d_viewer.ui"
WINDOW_UI = ROOT / "data" / "ui" / "window.ui"


def test_viewer_tracks_alt_and_double_click():
    src = VIEWER.read_text(encoding="utf-8")
    assert "ALT_MASK" in src
    assert "_pref_toggled_by_alt" in src
    assert "on_click_pressed" in src
    assert "around_cursor=" in src
    assert "to_cursor=" in src
    assert "use_cursor_depth=" in src
    assert "reset_to_bounds()" in src
    # Classic path locks pivot to focal so the model stays centered.
    assert "pivot = foc" in src


def test_f3d_ui_has_lmb_double_click_gesture():
    ui = VIEWER_UI.read_text(encoding="utf-8")
    assert 'class="GtkGestureClick"' in ui
    assert 'handler="on_click_pressed"' in ui
    assert 'name="button">1</property>' in ui


def test_prefs_describe_classic_centered_orbit():
    ui = WINDOW_UI.read_text(encoding="utf-8")
    assert "classic centered orbit" in ui
    assert "hold Alt to zoom the view center" in ui


def test_orbit_around_cursor_default_is_off():
    from exhibit.camera_nav import NAV_SETTING_DEFAULTS

    assert NAV_SETTING_DEFAULTS["nav-orbit-around-cursor"] is False
    gschema = (ROOT / "data" / "io.github.nokse22.Exhibit.gschema.xml").read_text(
        encoding="utf-8"
    )
    assert (
        'name="nav-orbit-around-cursor" type="b">\n      <default>false</default>'
        in gschema
    )
