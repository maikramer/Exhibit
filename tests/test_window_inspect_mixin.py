# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for InspectMixin."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_inspect.py"
WINDOW = ROOT / "src" / "window.py"

EXPECTED = {
    "_refresh_mesh_stats",
    "_apply_stats_overlay",
    "_apply_armature_mode",
    "_apply_display_depth_mode",
    "_apply_normal_glyphs_mode",
    "_apply_skin_weights_mode",
    "_refresh_skin_weights_joint_combo",
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


def test_inspect_mixin_methods():
    missing = EXPECTED - _class_methods(MIXIN, "InspectMixin")
    assert not missing, missing


def test_window_uses_inspect_without_duplicates():
    src = WINDOW.read_text(encoding="utf-8")
    assert "InspectMixin" in src
    assert not (_class_methods(WINDOW, "Viewer3dWindow") & EXPECTED)


def test_armature_and_stats_bodies_intact():
    src = MIXIN.read_text(encoding="utf-8")
    assert "No armature found in this model" in src
    assert "collect_mesh_stats" in src
    assert "format_overlay_text" in src
    assert "xray_opacity" in src
    assert "skin.skeleton" in src
    assert "scivis-enabled" in src
    assert "WEIGHTS_0" in src or "WEIGHTS_ARRAY" in src
    assert "HEAT_ATTR" in src
    assert "write_skin_weight_heat_temp" in src
    assert "normal-glyphs-scale" in src
