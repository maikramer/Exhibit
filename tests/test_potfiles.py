# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POTFILES = ROOT / "po" / "POTFILES"
GETTEXT_IMPORT = re.compile(
    r"from gettext import|import gettext",
)


def test_potfiles_covers_src_modules_with_gettext():
    listed = {
        line.strip()
        for line in POTFILES.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    missing: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if not GETTEXT_IMPORT.search(text):
            continue
        if "_(" not in text and "ngettext(" not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel not in listed:
            missing.append(rel)
    assert missing == [], f"add to po/POTFILES: {missing}"


def test_potfiles_skips_modules_without_i18n():
    """Helpers like file_patterns.py must not pollute POTFILES."""
    listed = {
        line.strip()
        for line in POTFILES.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "src/file_patterns.py" not in listed
    text = (ROOT / "src" / "file_patterns.py").read_text(encoding="utf-8")
    assert "gettext" not in text
    assert "_(" not in text
