# SPDX-License-Identifier: GPL-3.0-or-later
"""Armature x-ray forces DDP; OFF must restore prior blending nick/bool."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "src" / "window_inspect.py"


def test_armature_snapshots_and_restores_translucency_support():
    src = INSPECT.read_text(encoding="utf-8")
    body = src.split("def _apply_armature_mode", 1)[1].split("def ", 1)[0]
    # Snapshot on enable (before force DDP).
    snap = body.split("if self._armature_xray_restore is None:", 1)[1].split(
        "if tab is not None:", 1
    )[0]
    assert '"translucency-support"' in snap
    # Force DDP while on.
    assert '"translucency-support": True' in body
    # Restore path writes setting + fanout.
    assert 'set_setting("translucency-support", blend)' in body
    assert '"translucency-support": blend' in body
