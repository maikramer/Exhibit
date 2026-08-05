# SPDX-License-Identifier: GPL-3.0-or-later
"""Display Depth must restore Coloration/scivis instead of forcing it off."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "src" / "window_inspect.py"


def test_display_depth_restores_scivis_not_hard_false():
    src = INSPECT.read_text(encoding="utf-8")
    body = src.split("def _apply_display_depth_mode", 1)[1].split("def ", 1)[0]
    assert "_depth_scivis_restore" in body
    # Disable path must not unconditionally kill scivis.
    off = body.split("return", 1)[1]  # after enable early-return
    assert '"scivis-enabled": False' not in off
    assert "scivis_restore" in off
