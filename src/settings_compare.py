# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare window setting values (no GTK)."""

from __future__ import annotations

from typing import Any


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
