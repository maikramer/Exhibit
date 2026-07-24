# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for LifecycleMixin."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIXIN = ROOT / "src" / "window_lifecycle.py"
WINDOW = ROOT / "src" / "window.py"

EXPECTED = {
    "_init_home_button",
    "on_home_clicked",
    "on_restore_session_toggled",
    "on_close_request",
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


def test_lifecycle_mixin_methods():
    missing = EXPECTED - _class_methods(MIXIN, "LifecycleMixin")
    assert not missing, missing


def test_window_uses_lifecycle_without_duplicates():
    src = WINDOW.read_text(encoding="utf-8")
    assert "LifecycleMixin" in src
    assert not (_class_methods(WINDOW, "Viewer3dWindow") & EXPECTED)


def test_close_request_persists_session_and_cache():
    src = MIXIN.read_text(encoding="utf-8")
    assert "_persist_session_files" in src
    assert "clear_prepare_cache" in src
    assert "isinstance(w, type(self))" in src
    assert "Viewer3dWindow" not in src or "Viewer3dWindow still alive" in src


def test_home_button_wired_in_code_not_template_callback():
    mixin = MIXIN.read_text(encoding="utf-8")
    ui = (ROOT / "data" / "ui" / "window.ui").read_text(encoding="utf-8")
    window = WINDOW.read_text(encoding="utf-8")
    assert "_init_home_button" in mixin
    assert '@Gtk.Template.Callback("on_home_clicked")' not in mixin
    assert 'handler="on_home_clicked"' not in ui
    assert "home_button_headerbar" in window
    assert "_init_home_button()" in window
