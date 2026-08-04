# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for tab context menu / reopen closed."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABS = ROOT / "src" / "window_tabs.py"
WINDOW = ROOT / "src" / "window.py"
OVERLAY = ROOT / "data" / "gtk" / "help-overlay.ui"


def test_tab_context_menu_setup_exists():
    src = TABS.read_text(encoding="utf-8")
    assert "_setup_tab_context_menu" in src
    assert "set_menu_model" in src
    assert "setup-menu" in src
    assert "win.tab-close" in src
    assert "win.tab-close-other" in src
    assert "win.tab-close-before" in src
    assert "win.tab-close-after" in src
    assert "win.tab-reopen-closed" in src
    assert "close_other_pages" in src
    assert "close_pages_before" in src
    assert "close_pages_after" in src
    assert "_push_closed_tab" in src
    assert "_CLOSED_TABS_MAX" in src


def test_window_wires_tab_context_menu():
    src = WINDOW.read_text(encoding="utf-8")
    assert "_setup_tab_context_menu" in src
    assert "_closed_tabs" in src


def test_close_page_pushes_closed_stack():
    src = TABS.read_text(encoding="utf-8")
    tree = ast.parse(src)
    mixin = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    close = next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef) and n.name == "on_tab_close_page"
    )
    body = ast.get_source_segment(src, close)
    assert body is not None
    assert "_push_closed_tab" in body


def test_help_overlay_has_tab_shortcuts():
    ui = OVERLAY.read_text(encoding="utf-8")
    assert "win.tab-close" in ui
    assert "win.tab-close-other" in ui
    assert "win.tab-reopen-closed" in ui
    assert "Close Tab (right-click tab)" in ui
    assert "Reopen Closed Tab" in ui
    assert "&lt;Primary&gt;&lt;Shift&gt;t" in ui
