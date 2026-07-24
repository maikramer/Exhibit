# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for LoadMixin (no Gtk runtime)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_load.py"
WINDOW = ROOT / "src" / "window.py"

EXPECTED = {
    "open_file_chooser",
    "open_folder_chooser",
    "on_open_folder_response",
    "_open_model_paths",
    "_advance_open_queue",
    "on_open_files_response",
    "load_file",
    "_resolve_readable_path",
    "_start_warm_load",
    "_warm_load_tick",
    "_warm_prepare_finished",
    "_remember_recent_file",
    "_refresh_recent_files_ui",
    "_on_recent_file_activated",
    "on_file_opened",
    "_post_open_sidebar_refresh",
    "on_file_not_opened",
    "on_open_button_clicked",
    "on_drop_received",
    "on_drop_enter",
    "on_drop_leave",
    "load_hdri",
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


def test_load_mixin_has_open_methods():
    methods = _class_methods(MIXIN, "LoadMixin")
    missing = EXPECTED - methods
    assert not missing, missing


def test_window_uses_load_mixin_without_duplicates():
    src = WINDOW.read_text(encoding="utf-8")
    assert "from .window_load import LoadMixin" in src
    assert "LoadMixin" in src.split("class Viewer3dWindow", 1)[1].split(":", 1)[0]
    overlap = _class_methods(WINDOW, "Viewer3dWindow") & EXPECTED
    assert not overlap, overlap


def test_resolve_readable_path_delegates_to_path_utils():
    src = MIXIN.read_text(encoding="utf-8")
    assert "from .path_utils import resolve_readable_path" in src
    tree = ast.parse(src)
    mixin = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    fn = next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef) and n.name == "_resolve_readable_path"
    )
    body = ast.get_source_segment(src, fn)
    assert body is not None
    assert "return resolve_readable_path(filepath)" in body
