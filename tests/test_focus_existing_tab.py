# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for focus-existing-tab (no duplicate open)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABS = ROOT / "src" / "window_tabs.py"
WINDOW = ROOT / "src" / "window.py"
GSCHEMA = ROOT / "data" / "io.github.nokse22.Exhibit.gschema.xml"


def test_gschema_has_focus_existing_tab():
    src = GSCHEMA.read_text(encoding="utf-8")
    assert 'name="focus-existing-tab"' in src
    assert "<default>true</default>" in src


def test_window_implements_focus_existing():
    src = WINDOW.read_text(encoding="utf-8")
    assert "focus-existing-tab" in src
    assert "samefile" in src or "_open_in_new_tab" in src


def test_tabs_mixin_keeps_focus_helpers():
    src = TABS.read_text(encoding="utf-8")
    for name in (
        "_find_tab_by_filepath",
        "_focus_existing_tab",
        "_flash_tab_attention",
        "_norm_tab_path",
    ):
        assert name in src
