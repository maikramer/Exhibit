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


def test_pin_restore_does_not_reuse_filepath_as_prepared():
    """After restart, pin must re-prepare — not skip via prepared_path=filepath."""
    src = TABS.read_text(encoding="utf-8")
    tree = ast.parse(src)
    mixin = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    restore = next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef) and n.name == "_restore_split_compare_pin"
    )
    body = ast.get_source_segment(src, restore)
    assert body is not None
    assert "_split_compare_pin_prepared = None" in body
    assert "_split_compare_pin_prepared = path" not in body

    load = next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "_load_split_compare_from_active"
    )
    load_body = ast.get_source_segment(src, load)
    assert load_body is not None
    assert "prepared = None" in load_body


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


def test_split_and_new_tab_seed_nav_and_point_up():
    src = TABS.read_text(encoding="utf-8")
    assert "_apply_point_up_to_viewer" in src
    assert "apply_nav_settings" in src
    ensure = src.split("def _ensure_split_compare_viewer")[1].split(
        "def _teardown_split_compare_viewer"
    )[0]
    assert "apply_nav_settings" in ensure
    assert "_apply_point_up_to_viewer" in ensure
    add = src.split("def _add_viewer_tab")[1].split("def _on_sync_cameras_change")[0]
    assert "_apply_point_up_to_viewer" in add


def test_split_load_initializes_and_retries_realize():
    src = TABS.read_text(encoding="utf-8")
    load = src.split("def _load_split_compare_from_active")[1].split(
        "def _sync_peer_cameras_from_active"
    )[0]
    assert "viewer.initialize()" in load
    assert "get_realized()" in load
    assert "_split_load_realize_attempts" in load
    assert "retain_prepared" in load
    assert "release_prepared" in load
    load_mixin = (ROOT / "src" / "widgets" / "f3d_viewer_load.py").read_text(
        encoding="utf-8"
    )
    assert "if self.scene is None" in load_mixin
