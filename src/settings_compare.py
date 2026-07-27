# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare window setting values (no GTK)."""

from __future__ import annotations

import os
import re
from typing import Any


_PRESET_KEY_RE = re.compile(r"[^a-z0-9_]+")
_LEGACY_FORMATS_RE = re.compile(r"^\.\*\(([^)]+)\)$")


def preset_key_from_name(name: str) -> str:
    """Map a display name to a safe filename stem (no path separators)."""
    key = _PRESET_KEY_RE.sub("_", (name or "").lower().strip()).strip("_")
    return key or "preset"


def formats_entry_to_pattern(formats: str) -> str:
    """Build auto-best regex from a user formats entry (``glb, gltf`` / ``glb,gltf``).

    Patterns are extension-anchored (``.*\\.(glb|gltf)$``) so path segments like
    ``office`` do not false-match ``off``.
    """
    parts: list[str] = []
    for raw in formats.replace(";", ",").split(","):
        token = raw.strip().lstrip(".").lower()
        if token:
            parts.append(re.escape(token))
    if not parts:
        return ".*()"
    return rf".*\.({'|'.join(parts)})$"


def normalize_formats_pattern(pattern: str) -> str:
    """Upgrade legacy ``.*(ext|...)`` to ``.*\\.(ext|...)$``."""
    if not pattern or pattern == ".*()":
        return pattern
    if pattern.startswith(".*\\.") and pattern.endswith("$"):
        return pattern
    match = _LEGACY_FORMATS_RE.fullmatch(pattern)
    if match:
        return rf".*\.({match.group(1)})$"
    return pattern


def formats_pattern_matches(pattern: str, filepath: str) -> bool:
    """True if basename of ``filepath`` matches a formats auto-best pattern."""
    pattern = normalize_formats_pattern(pattern or "")
    if pattern == ".*()":
        return False
    name = os.path.basename(filepath or "")
    try:
        return re.search(pattern, name, flags=re.IGNORECASE) is not None
    except re.error:
        return False


def settings_values_equal(a: Any, b: Any) -> bool:
    """Compare setting values; normalize RGB list/tuple mismatches from JSON."""
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        try:
            return all(abs(float(x) - float(y)) < 1e-6 for x, y in zip(a, b))
        except (TypeError, ValueError):
            return tuple(a) == tuple(b)
    return a == b
