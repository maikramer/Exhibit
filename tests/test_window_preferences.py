# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_preferences.py"
WINDOW = ROOT / "src" / "window.py"
WINDOW_UI = ROOT / "data" / "ui" / "window.ui"
F3D_UI = ROOT / "data" / "ui" / "f3d_viewer.ui"

EXPECTED = {
    "on_preferences_clicked",
    "_setup_theme_menu",
    "_sync_theme_toggle_button",
    "_load_nav_settings_from_gschema",
    "_persist_nav_settings_to_gschema",
    "_apply_nav_settings_to_viewers",
}


def _class_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                n.name
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"{class_name} not found in {path}")


def test_preferences_mixin_methods():
    assert not (EXPECTED - _class_methods(MIXIN, "PreferencesMixin"))
    src = MIXIN.read_text(encoding="utf-8")
    assert "on_theme_toggle_clicked" not in src
    assert "dark-mode-symbolic" not in src
    assert "preferences-desktop-appearance-symbolic" in src


def test_window_uses_preferences_mixin():
    src = WINDOW.read_text(encoding="utf-8")
    assert "PreferencesMixin" in src
    assert "preferences_dialog" in src
    assert "theme_toggle_button" in src


def test_window_ui_has_preferences_dialog_not_more_tab():
    ui = WINDOW_UI.read_text(encoding="utf-8")
    assert 'id="preferences_dialog"' in ui
    assert 'class="AdwPreferencesDialog"' in ui
    assert 'name">more</property>' not in ui
    assert 'id="theme_toggle_button"' in ui
    assert 'class="GtkMenuButton" id="theme_toggle_button"' in ui
    assert 'id="theme_menu"' not in ui  # built in Python with icons
    assert 'action-name">win.preferences' in ui
    assert 'handler="on_theme_toggle_clicked"' not in ui
    assert 'handler="on_preferences_clicked"' not in ui
    assert 'action">win.preferences' not in ui  # not in primary_menu
    assert 'action">app.theme' not in ui  # theme only via header menu
    assert "emblem-system-symbolic" not in ui
    assert "dark-mode-symbolic" not in ui
    assert 'id="nav_invert_y_switch"' in ui
    assert "Open HDRI Folder" in ui


def test_scroll_controller_not_kinetic():
    ui = F3D_UI.read_text(encoding="utf-8")
    assert "kinetic" not in ui
    assert "both-axes | horizontal | vertical" in ui
