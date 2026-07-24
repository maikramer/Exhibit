# SPDX-License-Identifier: GPL-3.0-or-later
"""About-dialog constants (no GTK)."""

from __future__ import annotations

from gettext import gettext as _

UPSTREAM_REPO = "https://github.com/Nokse22/Exhibit"
FORK_REPO = "https://github.com/maikramer/Exhibit"
FORK_ISSUES = f"{FORK_REPO}/issues"


def about_comments() -> str:
    """Localized short description for Adw.AboutDialog comments."""
    return _(
        "Gamedev fork: multi-tab previews, packed-GLB prepare "
        "(meshopt / KTX2), session restore, camera sync, "
        "experimental Split Compare, and exhibit render CLI "
        "with turntable video."
    )
