# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for the navigation cube overlay."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUBE = ROOT / "src" / "widgets" / "nav_cube.py"
TAB = ROOT / "src" / "widgets" / "viewer_tab.py"
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"
WINDOW_UI = ROOT / "src" / "window.ui"


def test_nav_cube_module_exists_with_faces_and_hit():
    src = CUBE.read_text(encoding="utf-8")
    assert "class NavCube" in src
    assert "front_view" in src
    assert "bottom_view" in src
    assert "sync_from_camera_state" in src
    assert "_face_at" in src


def test_viewer_tab_hosts_nav_cube():
    src = TAB.read_text(encoding="utf-8")
    assert "NavCube" in src
    assert "nav_cube" in src
    assert "nav_chrome" in src
    assert "sync_nav_cube" in src
    assert "set_nav_cube_chrome_inset" in src
    assert "free_fly_button" in src
    assert "airplane-mode-symbolic" in src
    assert "_enter_free_fly" in src
    assert "_exit_free_fly" in src
    assert "_free_fly_camera_restore" in src
    assert "_fly_tick" in src
    assert "fly_look" in src
    assert "fly_move" in src
    assert "EventControllerMotion" in src
    assert "_on_fly_pointer_motion" in src
    assert "_set_fly_look_active" in src
    assert "_fly_look_active" in src
    assert "add_tick_callback" in src
    assert "_fly_frame" in src
    assert 'set_property("interactive", False)' in src


def test_nav_cube_chrome_sync_uses_header_height():
    tabs = (ROOT / "src" / "window_tabs.py").read_text(encoding="utf-8")
    assert "def _sync_nav_cube_overlay_margin" in tabs
    assert "_header_bar_content_height" in tabs
    body = tabs.split("def _sync_nav_cube_overlay_margin", 1)[1].split(
        "def ", 1
    )[0]
    assert "set_nav_cube_chrome_inset" in body


def test_viewer_has_bottom_view():
    src = VIEWER.read_text(encoding="utf-8")
    assert "def bottom_view" in src
    assert 'apply_named_view("bottom")' in src


def test_window_ui_has_nav_cube_and_free_nav_switches():
    ui = WINDOW_UI.read_text(encoding="utf-8")
    assert 'id="free_navigation_switch"' in ui
    assert 'id="show_nav_cube_switch"' in ui
