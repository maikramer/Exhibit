# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for Exb-backed F3DViewer shim (no GPU / no Gtk)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"
MIXIN = ROOT / "src" / "widgets" / "f3d_viewer_load.py"

SHIM_EXPECTED = {
    "supports",
    "load_file",
    "add_file",
    "get_scene_parts",
    "get_scene_tree",
    "get_hidden_part_indices",
    "get_effective_hidden_part_indices",
    "get_prepared_path",
    "set_part_visible",
    "reset_to_bind_pose",
    "release_resources",
    "_release_prepared_path",
    "_refresh_scene_graph",
}

LEGACY_MIXIN_EXPECTED = {
    "_clear_force_reader",
    "_add_scene_buffer",
    "supports",
    "load_file",
    "set_part_visible",
    "reset_to_bind_pose",
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


def test_exb_shim_has_load_methods():
    methods = _class_methods(VIEWER, "F3DViewer")
    missing = SHIM_EXPECTED - methods
    assert not missing, missing


def test_exb_shim_does_not_import_python_f3d():
    viewer_src = VIEWER.read_text(encoding="utf-8")
    assert "import f3d" not in viewer_src
    assert "class F3DViewer(Gtk.Box)" in viewer_src or "class F3DViewer(" in viewer_src
    assert "Exb.View" in viewer_src


def test_legacy_load_mixin_kept_for_reference():
    """Legacy F3D Python mixin remains on disk for porting reference."""
    methods = _class_methods(MIXIN, "F3DLoadMixin")
    missing = LEGACY_MIXIN_EXPECTED - methods
    assert not missing, missing
    text = MIXIN.read_text(encoding="utf-8")
    assert "f3d = None" in text or "import f3d" in text
