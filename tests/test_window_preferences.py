# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_preferences.py"
WINDOW = ROOT / "src" / "window.py"
WINDOW_UI = ROOT / "src" / "window.ui"

EXPECTED = {
    "on_preferences_clicked",
    "_init_preferences_actions",
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
    assert "set_visible_child_name(\"more\")" in src
    assert "set_show_sidebar(True)" in src
    # Must not open Save Settings dialog as Preferences.
    assert "settings_dialog.present" not in src
    assert "preferences_dialog.present" not in src


def test_window_uses_preferences_mixin():
    src = WINDOW.read_text(encoding="utf-8")
    assert "PreferencesMixin" in src
    assert "sidebar_stack = Gtk.Template.Child()" in src
    assert "preferences_dialog = self.settings_dialog" not in src


def test_window_ui_has_more_tab_for_preferences():
    ui = WINDOW_UI.read_text(encoding="utf-8")
    assert 'id="sidebar_stack"' in ui
    assert 'name">more</property>' in ui
    assert 'action">win.preferences' in ui
    assert "Save Settings" in (
        ROOT / "src" / "widgets" / "settings_dialog.ui"
    ).read_text(encoding="utf-8")
