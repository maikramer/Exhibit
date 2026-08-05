# SPDX-License-Identifier: GPL-3.0-or-later
"""Model→Color→Coloration combo must be wired to scivis settings."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOW = ROOT / "src" / "window.py"
UI = ROOT / "src" / "window_settings_ui.py"


def test_scivis_combo_wired_in_window():
    src = WINDOW.read_text(encoding="utf-8")
    assert "model_scivis_component_combo = Gtk.Template.Child()" in src
    assert "model_color_row = Gtk.Template.Child()" in src
    wire = src.split("def _wire_fork_settings_widgets", 1)[1].split(
        "def ", 1
    )[0]
    assert "on_scivis_component_combo_changed" in wire
    assert "set_scivis_component_combo" in wire


def test_scivis_combo_handlers_block_feedback():
    src = UI.read_text(encoding="utf-8")
    assert "_block_scivis_combo" in src
    assert 'set_setting("scivis-enabled"' in src
