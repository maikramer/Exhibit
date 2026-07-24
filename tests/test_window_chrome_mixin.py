# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for ChromeMixin."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_chrome.py"
WINDOW = ROOT / "src" / "window.py"

EXPECTED = {
    "orthographic_state_changed",
    "on_orthographic_changed",
    "toggle_orthographic",
    "open_with_external_app",
    "on_play_button_clicked",
    "on_playing_changed",
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


def test_chrome_mixin_methods():
    missing = EXPECTED - _class_methods(MIXIN, "ChromeMixin")
    assert not missing, missing


def test_window_uses_chrome_without_duplicates():
    src = WINDOW.read_text(encoding="utf-8")
    assert "ChromeMixin" in src
    assert not (_class_methods(WINDOW, "Viewer3dWindow") & EXPECTED)
