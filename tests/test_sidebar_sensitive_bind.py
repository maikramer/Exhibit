# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar must sync sensitive from loading-file at construct time."""
from __future__ import annotations

from pathlib import Path

WINDOW_UI = Path(__file__).resolve().parents[1] / "src" / "window.ui"


def test_sidebar_sensitive_bind_has_sync_create():
    ui = WINDOW_UI.read_text(encoding="utf-8")
    # Without sync-create the XML default (historically False) sticks until the
    # first loading-file notify — Preferences/More before open stay dead.
    needle = (
        'bind-source="engine" bind-property="loading-file" '
        'bind-flags="invert-boolean | sync-create"'
    )
    assert needle in ui
    assert 'bind-property="loading-file" bind-flags="invert-boolean">' not in ui
