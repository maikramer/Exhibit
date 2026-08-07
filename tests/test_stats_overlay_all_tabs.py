# SPDX-License-Identifier: GPL-3.0-or-later
"""Stats overlay OFF must hide HUDs on every tab, not only the active one."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "src" / "window_inspect.py"


def test_stats_overlay_off_iterates_all_tabs():
    src = INSPECT.read_text(encoding="utf-8")
    body = src.split("def _apply_stats_overlay", 1)[1].split("def ", 1)[0]
    assert "_iter_tabs()" in body
    assert "stats_overlay_label.set_visible(False)" in body
    # Must not rely solely on the active-tab proxy property when disabling.
    off = body.split("return", 1)[1]
    assert "for tab in self._iter_tabs()" in off
