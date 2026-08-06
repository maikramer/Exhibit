# SPDX-License-Identifier: GPL-3.0-or-later
"""Armature/x-ray must fan out to every tab, not only the active viewer."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "src" / "window_inspect.py"


def test_apply_armature_mode_updates_all_viewers():
    src = INSPECT.read_text(encoding="utf-8")
    body = src.split("def _apply_armature_mode", 1)[1].split("def ", 1)[0]
    assert "_update_all_viewers_options" in body
    # Active-only + manual split path removed.
    assert "self.f3d_viewer.update_options(armature_opts)" not in body
    assert "split.update_options(armature_opts)" not in body
