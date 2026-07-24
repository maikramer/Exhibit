# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for LayoutMixin."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_layout.py"
WINDOW = ROOT / "src" / "window.py"

EXPECTED = {
    "on_close_sidebar_clicked",
    "on_apply_breakpoint",
    "on_unapply_breakpoint",
    "on_split_view_show_sidebar_changed",
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


def test_layout_mixin_methods():
    missing = EXPECTED - _class_methods(MIXIN, "LayoutMixin")
    assert not missing, missing


def test_window_uses_layout_without_duplicates():
    src = WINDOW.read_text(encoding="utf-8")
    assert "LayoutMixin" in src
    assert not (_class_methods(WINDOW, "Viewer3dWindow") & EXPECTED)


def test_layout_methods_are_small():
    tree = ast.parse(MIXIN.read_text(encoding="utf-8"))
    mixin = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    for node in mixin.body:
        if isinstance(node, ast.FunctionDef) and node.name in EXPECTED:
            assert (node.end_lineno - node.lineno + 1) <= 10, node.name
