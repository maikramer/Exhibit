# SPDX-License-Identifier: GPL-3.0-or-later
"""Skin-weights must snapshot/restore model-opacity (and unlit), like depth."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "src" / "window_inspect.py"


def test_skin_weights_restores_opacity_and_unlit():
    src = INSPECT.read_text(encoding="utf-8")
    mode = src.split("def _apply_skin_weights_mode", 1)[1].split("def ", 1)[0]
    assert '"model-opacity"' in mode
    assert '"model-unlit"' in mode
    # Snapshot on enable.
    assert (
        mode.split("if getattr(self, \"_skin_weights_scivis_restore\"", 1)[1]
        .split("mode = str", 1)[0]
        .count("model-opacity")
        >= 1
    )
    opts = src.split("def _apply_skin_weights_options", 1)[1].split("def ", 1)[0]
    assert '"model-unlit": True' in opts
    assert 'engine.options.update({"model.unlit"' not in opts
