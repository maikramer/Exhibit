# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

WINDOW = Path(__file__).resolve().parents[1] / "src" / "window.py"


def _methods() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(WINDOW.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Viewer3dWindow":
            return {
                n.name: n
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError("Viewer3dWindow missing")


def test_init_calls_setup_helpers():
    init = _methods()["__init__"]
    src = ast.get_source_segment(WINDOW.read_text(encoding="utf-8"), init)
    assert "_setup_window_actions()" in src
    assert "_wire_settings_widgets()" in src
    assert (init.end_lineno - init.lineno + 1) < 220


def test_setup_helpers_exist_and_define_actions_once():
    methods = _methods()
    assert "_setup_window_actions" in methods
    assert "_wire_settings_widgets" in methods
    # Regression: helper bodies must be indented (not class-level Assign).
    setup = methods["_setup_window_actions"]
    assert any(isinstance(n, ast.Assign) for n in setup.body), setup.body
    assert not any(isinstance(n, ast.FunctionDef) for n in setup.body)
    text = WINDOW.read_text(encoding="utf-8")
    assert text.count("win.sync-cameras") == 1
    assert text.count("win.open-folder") == 1
    # Exact action name (exclude win.split-compare-swap).
    assert text.count('"win.split-compare"') == 1
    assert text.count('"win.split-compare-swap"') == 1
    assert "split_compare_revealer" in text


def test_split_compare_handler_exists():
    tabs = (
        Path(__file__).resolve().parents[1] / "src" / "window_tabs.py"
    ).read_text(encoding="utf-8")
    assert "def _on_split_compare_change" in tabs
    assert "def _ensure_split_compare_viewer" in tabs
    assert "def _load_split_compare_from_active" in tabs
    assert "def _teardown_split_compare_viewer" in tabs
    assert "def _on_split_compare_pin_toggled" in tabs
    assert "def _size_split_compare_paned" in tabs
    assert "split_compare_pin_check" in (
        Path(__file__).resolve().parents[1] / "src" / "window.py"
    ).read_text(encoding="utf-8")
