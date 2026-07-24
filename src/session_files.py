# SPDX-License-Identifier: GPL-3.0-or-later
"""Last-session tab paths helpers (no GTK)."""

from __future__ import annotations

import os

from .drop_paths import DEFAULT_MAX_BATCH_OPEN

MAX_SESSION_FILES = DEFAULT_MAX_BATCH_OPEN


def collect_session_paths(
    filepaths: list[str | None],
    *,
    max_items: int = MAX_SESSION_FILES,
) -> list[str]:
    """Deduped absolute paths of existing model files (tab order)."""
    out: list[str] = []
    seen: set[str] = set()
    for filepath in filepaths:
        if not filepath:
            continue
        abs_path = os.path.abspath(filepath)
        if abs_path in seen or not os.path.isfile(abs_path):
            continue
        seen.add(abs_path)
        out.append(abs_path)
        if len(out) >= max_items:
            break
    return out


def existing_session(paths: list[str]) -> list[str]:
    """Keep only session paths that still exist as files."""
    return [path for path in paths if os.path.isfile(path)]


def session_paths_to_restore(
    enabled: bool, paths: list[str]
) -> list[str]:
    """Return existing session paths when restore is enabled; else empty."""
    if not enabled:
        return []
    return existing_session(paths)
