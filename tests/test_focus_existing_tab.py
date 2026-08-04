# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for focus-existing-tab (no duplicate open)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABS = ROOT / "src" / "window_tabs.py"
LOAD = ROOT / "src" / "window_load.py"
WINDOW = ROOT / "src" / "window.py"
UI = ROOT / "data" / "ui" / "window.ui"
GSCHEMA = ROOT / "data" / "io.github.nokse22.Exhibit.gschema.xml"


def test_gschema_has_focus_existing_tab():
    src = GSCHEMA.read_text(encoding="utf-8")
    assert 'name="focus-existing-tab"' in src
    assert "<default>true</default>" in src


def test_ui_has_focus_existing_switch():
    ui = UI.read_text(encoding="utf-8")
    assert 'id="focus_existing_tab_switch"' in ui
    assert "Focus Existing Tab" in ui


def test_window_binds_focus_existing_setting():
    src = WINDOW.read_text(encoding="utf-8")
    assert "focus_existing_tab_switch" in src
    assert "focus-existing-tab" in src


def test_tabs_mixin_has_focus_helpers():
    src = TABS.read_text(encoding="utf-8")
    for name in (
        "_find_tab_by_filepath",
        "_focus_existing_tab",
        "_flash_tab_attention",
        "_norm_tab_path",
    ):
        assert name in src
    assert "set_needs_attention" in src
    assert "Already open:" in src


def test_load_file_short_circuits_duplicate():
    src = LOAD.read_text(encoding="utf-8")
    tree = ast.parse(src)
    mixin = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    load = next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef) and n.name == "load_file"
    )
    body = ast.get_source_segment(src, load)
    assert body is not None
    assert "focus-existing-tab" in body
    assert "_find_tab_by_filepath" in body
    assert "_focus_existing_tab" in body
