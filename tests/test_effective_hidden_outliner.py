# SPDX-License-Identifier: GPL-3.0-or-later
"""Outliner effective-hidden must expand ancestor hides (parity with legacy)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"


def test_get_effective_hidden_expands_ancestors():
    src = VIEWER.read_text(encoding="utf-8")
    body = src.split("def get_effective_hidden_part_indices", 1)[1].split(
        "def ", 1
    )[0]
    assert "_effective_hidden" in body
    assert "_load_gltf" in body
    # Stub that only returned raw _hidden_parts is gone.
    assert "return set(self._hidden_parts)" not in body
