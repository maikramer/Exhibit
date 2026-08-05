# SPDX-License-Identifier: GPL-3.0-or-later
"""GDK_DEBUG bootstrap must not overwrite user/Flatpak env."""

from __future__ import annotations

from pathlib import Path

INIT = Path(__file__).resolve().parents[1] / "src" / "__init__.py"


def test_gdk_debug_default_does_not_overwrite():
    src = INIT.read_text(encoding="utf-8")
    assert 'getenv("GDK_DEBUG")' in src
    assert 'setenv("GDK_DEBUG", "gl-prefer-gl", False)' in src
    assert 'setenv("GDK_DEBUG", "gl-prefer-gl", True)' not in src
