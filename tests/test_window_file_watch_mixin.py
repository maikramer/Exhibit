# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_file_watch.py"
WINDOW = ROOT / "src" / "window.py"
EXPECTED = {"periodic_check_for_file_change", "update_time_stamp"}


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


def test_file_watch_mixin_methods():
    assert not (EXPECTED - _class_methods(MIXIN, "FileWatchMixin"))


def test_window_uses_file_watch_without_duplicates():
    assert "FileWatchMixin" in WINDOW.read_text(encoding="utf-8")
    assert not (_class_methods(WINDOW, "Viewer3dWindow") & EXPECTED)
