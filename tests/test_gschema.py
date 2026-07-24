# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "io.github.nokse22.Exhibit.gschema.xml"
)


def test_gschema_lists_session_and_recent_keys():
    text = SCHEMA.read_text(encoding="utf-8")
    for key in (
        'name="recent-files"',
        'name="session-files"',
        'name="restore-session"',
        'name="split-compare-sash-ratio"',
        'name="split-compare-enabled"',
        'name="split-compare-pinned"',
        'name="split-compare-pin-path"',
        'name="nav-invert-x"',
        'name="nav-invert-y"',
        'name="nav-zoom-to-cursor"',
        'name="nav-orbit-around-cursor"',
        'name="nav-touchpad-orbit"',
        'name="nav-mmb-click-pivot"',
        'name="nav-orbit-sensitivity"',
        'name="nav-zoom-sensitivity"',
        'name="nav-pan-sensitivity"',
        'type="as"',
        'type="b"',
        'type="d"',
        'type="s"',
    ):
        assert key in text
    assert "io.github.nokse22.Exhibit" in text
