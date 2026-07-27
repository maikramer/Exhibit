# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse Gdk-style rgb/rgba color strings without importing GTK."""

from __future__ import annotations


def list_to_rgb(lst):
    """Format an RGB sequence as ``rgb(r,g,b)``; pad short/missing channels with 0."""
    vals = list(lst or ())
    while len(vals) < 3:
        vals.append(0.0)
    return (
        f"rgb({int(float(vals[0]) * 255)},"
        f"{int(float(vals[1]) * 255)},"
        f"{int(float(vals[2]) * 255)})"
    )


def rgb_to_list(rgb):
    """Parse ``rgb(...)`` / ``rgba(...)`` into 0–1 floats (alpha ignored)."""
    text = (rgb or "").strip()
    if text.startswith("rgba(") and text.endswith(")"):
        body = text[5:-1]
    elif text.startswith("rgb(") and text.endswith(")"):
        body = text[4:-1]
    else:
        raise ValueError(f"unsupported color string: {rgb!r}")

    parts = [p.strip() for p in body.split(",")]
    if len(parts) < 3:
        raise ValueError(f"unsupported color string: {rgb!r}")

    return tuple(int(float(parts[i])) / 255 for i in range(3))
