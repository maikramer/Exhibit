# SPDX-License-Identifier: GPL-3.0-or-later
"""Ensure help-overlay UI strings stay in the translation catalog."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "data" / "gtk" / "help-overlay.ui"
POT = ROOT / "po" / "Exhibit.pot"
PT_BR = ROOT / "po" / "pt_BR.po"
POTFILES = ROOT / "po" / "POTFILES"

_TRANS_PROP = re.compile(
    r'<property name="(?:title|label)" translatable="yes">(.*?)</property>',
    re.DOTALL,
)


def _overlay_msgids() -> list[str]:
    text = OVERLAY.read_text(encoding="utf-8")
    out: list[str] = []
    for match in _TRANS_PROP.finditer(text):
        raw = match.group(1).strip()
        if raw:
            out.append(raw)
    return out


def _active_msgids(po_text: str) -> set[str]:
    """Parse non-obsolete msgid entries (single-line only is enough here)."""
    found: set[str] = set()
    for match in re.finditer(
        r'^(?!#~ )msgid "(.*?)"\s*$', po_text, re.MULTILINE
    ):
        found.add(match.group(1))
    return found


def _obsolete_msgids(po_text: str) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(
        r'^#~ msgid "(.*?)"\s*$', po_text, re.MULTILINE
    ):
        found.add(match.group(1))
    return found


def test_help_overlay_listed_in_potfiles():
    listed = POTFILES.read_text(encoding="utf-8")
    assert "data/gtk/help-overlay.ui" in listed


def test_help_overlay_strings_in_pot_not_obsolete_in_pt_br():
    msgids = _overlay_msgids()
    assert msgids, "expected translatable titles/labels in help-overlay.ui"
    # Split Compare strings that previously went obsolete after msgmerge.
    assert "Split Compare (Experimental)" in msgids
    assert "Swap Active ↔ Pinned" in msgids
    assert any("reopen silently" in m for m in msgids)

    pot = POT.read_text(encoding="utf-8")
    pt = PT_BR.read_text(encoding="utf-8")
    pot_active = _active_msgids(pot)
    pt_obsolete = _obsolete_msgids(pt)

    missing_pot = [m for m in msgids if m not in pot_active]
    obsolete = [m for m in msgids if m in pt_obsolete]
    assert missing_pot == [], f"add to po/Exhibit.pot: {missing_pot}"
    assert obsolete == [], f"revive in po/pt_BR.po (not #~): {obsolete}"
