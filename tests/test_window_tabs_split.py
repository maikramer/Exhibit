# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for Split Compare helpers in TabsMixin."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABS = ROOT / "src" / "window_tabs.py"
WINDOW = ROOT / "src" / "window.py"
UI = ROOT / "data" / "ui" / "window.ui"


def test_update_all_viewers_options_includes_split():
    src = TABS.read_text(encoding="utf-8")
    assert "_split_compare_viewer" in src
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "TabsMixin":
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "_update_all_viewers_options"
                ):
                    body = ast.dump(item)
                    assert "_split_compare_viewer" in body
                    return
    raise AssertionError("_update_all_viewers_options not found")


def test_split_compare_side_by_side_ui():
    ui = UI.read_text(encoding="utf-8")
    assert 'id="split_compare_main_paned"' in ui
    assert 'id="split_compare_column"' in ui
    assert 'id="tab_view"' in ui
    tab_pos = ui.index('id="tab_view"')
    rev_pos = ui.index('id="split_compare_revealer"')
    assert tab_pos < rev_pos
    assert "slide-left" in ui


def test_window_template_has_split_column():
    src = WINDOW.read_text(encoding="utf-8")
    assert "split_compare_column" in src
    assert "split_compare_main_paned" in src


def test_size_helper_uses_main_paned():
    src = TABS.read_text(encoding="utf-8")
    assert "split_compare_main_paned" in src
    assert "split-compare-sash-ratio" in src
    assert "_persist_split_compare_sash_ratio" in src
    assert "_on_split_compare_sash_changed" in src
    assert "queue_render" in src


def test_restore_split_compare_helper():
    src = TABS.read_text(encoding="utf-8")
    assert "_maybe_restore_split_compare" in src
    assert "split-compare-enabled" in src
    assert "_restore_split_compare_pin" in src
    assert "split-compare-pin-path" in src
    assert "os.path.isfile" in src
    win = WINDOW.read_text(encoding="utf-8")
    assert "_maybe_restore_split_compare" in win


def test_split_compare_swap_helper():
    src = TABS.read_text(encoding="utf-8")
    assert "_on_split_compare_swap" in src
    assert "_update_split_compare_swap_enabled" in src
    assert "Swapped active and pinned" in src
    assert "Pin another file to enable swap" in src
    assert "set_tooltip_text" in src
    assert "os.path.normpath" in src
    assert "os.path.isfile" in src
    win = WINDOW.read_text(encoding="utf-8")
    assert "split-compare-swap" in win
    assert "split_compare_swap_button" in win
    ui = UI.read_text(encoding="utf-8")
    assert "split-compare-swap" in ui
    assert 'id="split_compare_swap_button"' in ui
