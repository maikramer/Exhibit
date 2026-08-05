# SPDX-License-Identifier: GPL-3.0-or-later
"""Use Custom Color switch must be wired and gschema-backed."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOW = ROOT / "src" / "window.py"
LIFECYCLE = ROOT / "src" / "window_lifecycle.py"
SCHEMA = ROOT / "data" / "io.github.nokse22.Exhibit.gschema.xml"


def test_use_color_switch_is_template_child_and_wired():
    src = WINDOW.read_text(encoding="utf-8")
    assert "use_color_switch = Gtk.Template.Child()" in src
    assert '(self.use_color_switch, "use-color")' in src
    assert 'get_boolean("use-color")' in src


def test_use_color_persists_on_close():
    src = LIFECYCLE.read_text(encoding="utf-8")
    assert '"use-color"' in src
    assert 'get_setting("use-color")' in src


def test_gschema_defines_use_color():
    assert 'name="use-color"' in SCHEMA.read_text(encoding="utf-8")
