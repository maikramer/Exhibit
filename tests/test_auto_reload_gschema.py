# SPDX-License-Identifier: GPL-3.0-or-later
"""auto-reload must round-trip via gschema like auto-best."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOW = ROOT / "src" / "window.py"
LIFECYCLE = ROOT / "src" / "window_lifecycle.py"
SCHEMA = ROOT / "data" / "io.github.nokse22.Exhibit.gschema.xml"


def test_gschema_defines_auto_reload():
    assert 'name="auto-reload"' in SCHEMA.read_text(encoding="utf-8")


def test_window_seeds_auto_reload_from_gschema():
    src = WINDOW.read_text(encoding="utf-8")
    assert 'get_boolean("auto-reload")' in src
    assert 'set_setting(\n            "auto-reload"' in src or 'set_setting("auto-reload"' in src


def test_lifecycle_persists_auto_reload():
    src = LIFECYCLE.read_text(encoding="utf-8")
    assert 'set_boolean(\n            "auto-reload"' in src or 'set_boolean("auto-reload"' in src
