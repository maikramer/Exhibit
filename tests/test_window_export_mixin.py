# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_export.py"
WINDOW = ROOT / "src" / "window.py"
EXPECTED = {
    "send_toast",
    "save_as_image",
    "open_save_file_chooser",
    "on_save_file_response",
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


def test_export_mixin_methods():
    assert not (EXPECTED - _class_methods(MIXIN, "ExportMixin"))


def test_window_uses_export_without_duplicates():
    assert "ExportMixin" in WINDOW.read_text(encoding="utf-8")
    assert not (_class_methods(WINDOW, "Viewer3dWindow") & EXPECTED)


def test_save_toast_is_translatable():
    src = MIXIN.read_text(encoding="utf-8")
    assert '_("Image Saved")' in src
    assert '_("Open")' in src
