# SPDX-License-Identifier: GPL-3.0-or-later
"""Animation combo must follow the active tab engine, not only WindowSettings."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANIM = ROOT / "src" / "window_animation.py"


def test_refresh_animation_combo_reads_active_engine_index():
    src = ANIM.read_text(encoding="utf-8")
    assert "def _animation_index_from_active_viewer" in src
    body = src.split("def refresh_animation_combo", 1)[1].split("def ", 1)[0]
    assert "_animation_index_from_active_viewer" in body
    # Must not prefer the stale global setting as the sole source.
    assert 'get_setting("animation-index").value' not in body.split(
        "_animation_index_from_active_viewer", 1
    )[0]
    helper = src.split("def _animation_index_from_active_viewer", 1)[1].split(
        "def ", 1
    )[0]
    assert 'get_property("animation-index")' in helper
    assert "begin_view_batch" in body
