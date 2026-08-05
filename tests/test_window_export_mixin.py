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
    "_export_suggested_name",
    "_export_initial_folder",
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
    assert not (_class_methods(WINDOW, "ExbWindow") & EXPECTED)


def test_save_toast_is_translatable():
    src = MIXIN.read_text(encoding="utf-8")
    assert '_("Image Saved")' in src
    assert '_("Open")' in src


def test_save_response_guards_missing_local_path():
    src = MIXIN.read_text(encoding="utf-8")
    assert "if not file_path" in src
    assert '_("Could not save image")' in src


def test_save_as_image_handles_render_none():
    src = MIXIN.read_text(encoding="utf-8")
    assert "if img is None" in src
    assert "return False" in src
    assert 'hasattr(img, "save")' in src
    assert "save_to_filename" in src
    assert "save image failed" in src


def test_save_chooser_sets_initial_folder_from_model():
    src = MIXIN.read_text(encoding="utf-8")
    assert "set_initial_folder" in src
    assert "os.path.isdir(parent)" in src
    assert "_export_suggested_name" in src


def test_viewer_camera_state_guards_missing_engine_api():
    viewer = (ROOT / "src" / "widgets" / "f3d_viewer.py").read_text(
        encoding="utf-8"
    )
    assert "def get_camera_state" in viewer
    assert "def set_camera_state" in viewer
    assert 'getattr(eng, "get_camera_state", None)' in viewer
    assert "if state is None" in viewer
