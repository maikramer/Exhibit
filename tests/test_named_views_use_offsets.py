# SPDX-License-Identifier: GPL-3.0-or-later
"""GUI named views must use offset_for_view, not rotate() pixel deltas."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"
VIEWS = ROOT / "src" / "camera_views.py"


def test_viewer_named_views_use_offset_for_view():
    src = VIEWER.read_text(encoding="utf-8")
    assert "def apply_named_view" in src
    assert "offset_for_view" in src
    # Old broken path: rotate(yaw, pitch) treated as pointer deltas.
    assert "def _named_orbit" not in src
    for name in (
        "front",
        "right",
        "back",
        "left",
        "top",
        "bottom",
        "isometric",
    ):
        assert f'apply_named_view("{name}")' in src


def test_offset_for_view_has_bottom():
    src = VIEWS.read_text(encoding="utf-8")
    assert 'name == "bottom"' in src
    assert '"bottom"' in src
