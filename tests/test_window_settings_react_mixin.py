# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_settings_react.py"
WINDOW = ROOT / "src" / "window.py"
EXPECTED = {
    "update_background_color",
    "on_view_setting_changed",
    "on_other_setting_changed",
    "on_internal_setting_changed",
    "change_setting_state",
    "get_gimble_limit",
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


def test_settings_react_mixin_methods():
    assert not (EXPECTED - _class_methods(MIXIN, "SettingsReactMixin"))


def test_window_uses_settings_react_without_duplicates():
    assert "SettingsReactMixin" in WINDOW.read_text(encoding="utf-8")
    assert not (_class_methods(WINDOW, "Viewer3dWindow") & EXPECTED)


def test_react_uses_shared_up_dirs():
    src = MIXIN.read_text(encoding="utf-8")
    assert "from .camera_views import UP_DIRS" in src
    assert "_apply_armature_mode" in src
    assert "_apply_stats_overlay" in src
    assert "_apply_display_depth_mode" in src
    assert "_apply_normal_glyphs_mode" in src
    assert "_apply_skin_weights_mode" in src
    assert 'setting.name == "display-depth"' in src
    assert 'setting.name == "normal-glyphs"' in src
    assert 'setting.name == "skin-weights"' in src
