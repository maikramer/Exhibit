# SPDX-License-Identifier: GPL-3.0-or-later
"""Recent model paths helpers (no GTK)."""

from __future__ import annotations

import os

MAX_RECENT_FILES = 8


def push_recent(
    paths: list[str], new_path: str, *, max_items: int = MAX_RECENT_FILES
) -> list[str]:
    """Put ``new_path`` first, dedupe, and truncate to ``max_items``."""
    abs_path = os.path.abspath(new_path)
    out = [abs_path]
    for path in paths:
        candidate = os.path.abspath(path)
        if candidate == abs_path:
            continue
        out.append(candidate)
        if len(out) >= max_items:
            break
    return out[:max_items]


def existing_recent(paths: list[str]) -> list[str]:
    """Keep only paths that still exist as files."""
    return [path for path in paths if os.path.isfile(path)]


def clear_recent() -> list[str]:
    """Empty recent list (caller persists via GSettings)."""
    return []
