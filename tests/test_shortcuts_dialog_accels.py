# SPDX-License-Identifier: GPL-3.0-or-later
"""Shortcuts dialog must list live accelerators (no dead WASD/Ctrl+views)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHORTCUTS = ROOT / "src" / "shortcuts-dialog.ui"
WINDOW = ROOT / "src" / "window.py"


def test_shortcuts_camera_matches_window_accels():
    ui = SHORTCUTS.read_text(encoding="utf-8")
    win = WINDOW.read_text(encoding="utf-8")
    assert '("win.view-front", ["1"])' in win
    assert '("win.orthographic", ["5"])' in win
    assert "win.view-front" in ui
    assert ">1<" in ui or 'accelerator">1</' in ui or 'accelerator">1</property>' in ui
    assert "win.orthographic" in ui
    assert 'accelerator">5</property>' in ui
    assert "Free Nav Pan" in ui
    assert "Free Nav Zoom" in ui
    # Dead upstream claims must not return.
    assert "Primary&gt;1" not in ui
    assert "Primary&gt;5" not in ui
    assert "Primary&gt;w" not in ui
    assert "Camera Movements" not in ui
