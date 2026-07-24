# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for F3DLoadMixin (no GPU / no Gtk)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "widgets" / "f3d_viewer_load.py"
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"

EXPECTED = {
    "_clear_force_reader",
    "_add_scene_buffer",
    "supports",
    "_prepare_filepath",
    "_resolve_load_path",
    "_release_prepared_path",
    "release_resources",
    "load_file",
    "add_file",
    "get_scene_parts",
    "get_scene_tree",
    "get_hidden_part_indices",
    "get_effective_hidden_part_indices",
    "get_prepared_path",
    "set_part_visible",
    "reset_to_bind_pose",
    "_try_native_part_visibility",
    "_reload_with_part_visibility",
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


def test_f3d_load_mixin_has_load_methods():
    methods = _class_methods(MIXIN, "F3DLoadMixin")
    missing = EXPECTED - methods
    assert not missing, missing


def test_f3d_viewer_uses_mixin_and_no_duplicate_load_methods():
    viewer_src = VIEWER.read_text(encoding="utf-8")
    assert "from .f3d_viewer_load import F3DLoadMixin" in viewer_src
    assert "class F3DViewer(F3DLoadMixin, Gtk.GLArea)" in viewer_src
    viewer_methods = _class_methods(VIEWER, "F3DViewer")
    overlap = viewer_methods & EXPECTED
    assert not overlap, overlap


def test_reload_prefers_native_visibility_hook():
    tree = ast.parse(MIXIN.read_text(encoding="utf-8"))
    mixin = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    reload = next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef) and n.name == "_reload_with_part_visibility"
    )
    src = ast.get_source_segment(MIXIN.read_text(encoding="utf-8"), reload)
    assert src is not None
    assert "_try_native_part_visibility" in src
