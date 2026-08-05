# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_settings_react.py"
WINDOW = ROOT / "src" / "window.py"
# Engine-direct bg/preset live on ExbWindow — not duplicated in the mixin.
MIXIN_EXPECTED = {
    "on_view_setting_changed",
    "on_other_setting_changed",
    "on_internal_setting_changed",
    "get_gimble_limit",
    "_apply_point_up_to_viewer",
    "_apply_point_up_to_viewers",
}
WINDOW_OWNED = {
    "update_background_color",
    "change_setting_state",
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
    assert not (MIXIN_EXPECTED - _class_methods(MIXIN, "SettingsReactMixin"))
    # No dead duplicate of ExbWindow glue.
    assert not (WINDOW_OWNED & _class_methods(MIXIN, "SettingsReactMixin"))


def test_window_uses_settings_react_without_duplicates():
    assert "SettingsReactMixin" in WINDOW.read_text(encoding="utf-8")
    win_methods = _class_methods(WINDOW, "ExbWindow")
    assert not (MIXIN_EXPECTED & win_methods)
    assert WINDOW_OWNED <= win_methods


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
    assert "_apply_point_up_to_viewers" in src
    assert "_split_compare_viewer" in src
