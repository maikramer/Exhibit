# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect openable 3D model paths from file/folder drops (no GTK)."""

from __future__ import annotations

import os

# Soft cap so opening a huge asset tree cannot spawn unbounded tabs.
DEFAULT_MAX_BATCH_OPEN = 24


def collect_openable_model_paths(
    paths: list[str],
    *,
    allowed_exts: list[str],
    max_files: int | None = None,
) -> list[str]:
    """
    Expand directories; keep files whose extension is in ``allowed_exts``.

    When ``max_files`` is set, stop once that many matches are collected.
    """
    out: list[str] = []
    for filepath in paths:
        if os.path.isdir(filepath):
            for root, _dirs, names in os.walk(filepath):
                for name in sorted(names):
                    ext = os.path.splitext(name)[1][1:].lower()
                    if ext in allowed_exts:
                        out.append(os.path.join(root, name))
                        if max_files is not None and len(out) >= max_files:
                            return out
        else:
            ext = os.path.splitext(filepath)[1][1:].lower()
            if ext in allowed_exts:
                out.append(filepath)
                if max_files is not None and len(out) >= max_files:
                    return out
    return out
