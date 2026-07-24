# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for SettingsIOMixin."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_settings_io.py"
WINDOW = ROOT / "src" / "window.py"

EXPECTED = {
    "setup_configurations",
    "setup_hdri_folder",
    "on_save_settings_button_clicked",
    "on_save_settings_name_entry_changed",
    "on_save_settings_extensions_entry_changed",
    "on_save_settings",
    "set_settings_from_name",
    "check_for_options_change",
    "_settings_values_equal",
    "on_delete_skybox",
    "generate_thumbnail",
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


def test_settings_io_mixin_methods():
    missing = EXPECTED - _class_methods(MIXIN, "SettingsIOMixin")
    assert not missing, missing


def test_window_uses_settings_io_without_duplicates():
    src = WINDOW.read_text(encoding="utf-8")
    assert "SettingsIOMixin" in src
    assert not (_class_methods(WINDOW, "Viewer3dWindow") & EXPECTED)


def test_setup_hdri_folder_is_clean():
    """Regression: extract must not swallow reload_file into setup_hdri."""
    src = MIXIN.read_text(encoding="utf-8")
    assert "reload_file" not in src
    tree = ast.parse(src)
    mixin = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    hdri = next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef) and n.name == "setup_hdri_folder"
    )
    assert (hdri.end_lineno - hdri.lineno + 1) < 25
