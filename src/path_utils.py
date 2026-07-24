# SPDX-License-Identifier: GPL-3.0-or-later
"""Filesystem path helpers (no GTK)."""

from __future__ import annotations

import os


def resolve_readable_path(filepath: str) -> str | None:
    """Return a path the process can read (follow home→/media symlinks)."""
    if not filepath:
        return None
    candidates = [filepath]
    try:
        real = os.path.realpath(filepath)
        if real and real not in candidates:
            candidates.append(real)
    except OSError:
        pass
    for path in candidates:
        try:
            if os.path.isfile(path) and os.access(path, os.R_OK):
                return path
        except OSError:
            continue
    return None
