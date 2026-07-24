# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks for shared file extension helpers."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_file_patterns_module_lists_glb():
    src = (ROOT / "src" / "file_patterns.py").read_text(encoding="utf-8")
    assert "glb" in src
    assert "gltf" in src
    assert "image_patterns" in src


def test_mixins_do_not_import_extensions_from_window():
    for rel in ("src/window_load.py", "src/window_settings_io.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == "window":
                names = {a.name for a in node.names}
                assert "allowed_extensions" not in names, rel
                assert "image_patterns" not in names, rel
