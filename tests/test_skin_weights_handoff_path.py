# SPDX-License-Identifier: GPL-3.0-or-later
"""Skin-weight heat handoff must probe the active load path (incl. adhoc)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"
INSPECT = ROOT / "src" / "window_inspect.py"
TABS = ROOT / "src" / "window_tabs.py"


def test_viewer_exposes_active_load_path():
    src = VIEWER.read_text(encoding="utf-8")
    assert "def get_active_load_path" in src
    # Stable helper still strips adhoc; active must not.
    prepared = src.split("def get_prepared_path", 1)[1].split(
        "def get_active_load_path", 1
    )[0]
    assert "is_adhoc_load_temp" in prepared
    active = src.split("def get_active_load_path", 1)[1].split("def ", 1)[0]
    assert "is_adhoc_load_temp" not in active


def test_handoff_and_close_probe_active_load_path():
    assert "get_active_load_path" in INSPECT.read_text(encoding="utf-8")
    assert "get_active_load_path" in TABS.read_text(encoding="utf-8")
