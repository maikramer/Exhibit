# camera_views.py
#
# Copyright 2024-2025 Nokse <nokse@posteo.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Camera preset helpers shared by the GUI viewer and headless CLI render."""

from __future__ import annotations

import math
from typing import Any

from .vector_math import v_add, v_cross, v_mul, v_norm

UP_DIRS: dict[str, tuple[float, float, float]] = {
    "-X": (-1.0, 0.0, 0.0),
    "+X": (1.0, 0.0, 0.0),
    "-Y": (0.0, -1.0, 0.0),
    "+Y": (0.0, 1.0, 0.0),
    "-Z": (0.0, 0.0, -1.0),
    "+Z": (0.0, 0.0, 1.0),
}

PRESET_VIEWS = ("front", "right", "back", "left", "top", "isometric")


def _up_vector(up: str) -> tuple[float, float, float]:
    try:
        return UP_DIRS[up]
    except KeyError as exc:
        raise ValueError(f"Invalid up direction: {up}") from exc


def _horizontal_basis(
    up: str,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return (forward, right) axes orthogonal to ``up`` for orbit/cardinal views."""
    up_v = _up_vector(up)
    # Prefer world +Z as forward hint when up is Y; otherwise pick a stable axis.
    if abs(up_v[1]) > 0.5:
        forward_hint = (0.0, 0.0, 1.0)
    elif abs(up_v[2]) > 0.5:
        forward_hint = (0.0, 1.0, 0.0)
    else:
        forward_hint = (0.0, 1.0, 0.0)
    right = v_norm(v_cross(up_v, forward_hint))
    # If up parallel to hint, fall back.
    if all(abs(c) < 1e-9 for c in right):
        right = v_norm(v_cross(up_v, (1.0, 0.0, 0.0)))
    forward = v_norm(v_cross(right, up_v))
    return forward, right


def offset_for_view(
    name: str, up: str = "+Y", distance: float = 1000.0
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """
    Return ``(position_offset, view_up)`` for a named preset.

    Matches the historical Exhibit GUI camera presets (relative to up axis).
    """
    up_v = _up_vector(up)
    if name == "front":
        offset = v_mul(tuple([up_v[2], up_v[0], up_v[1]]), distance)
        return offset, up_v
    if name == "back":
        offset = v_mul(tuple([up_v[2], up_v[0], up_v[1]]), -distance)
        return offset, up_v
    if name == "right":
        offset = v_mul(tuple([up_v[1], up_v[2], up_v[0]]), distance)
        return offset, up_v
    if name == "left":
        offset = v_mul(tuple([up_v[1], up_v[2], up_v[0]]), -distance)
        return offset, up_v
    if name == "top":
        offset = v_mul(up_v, distance)
        view_up = v_norm(tuple([up_v[1], up_v[2], up_v[0]]))
        return offset, view_up
    if name == "isometric":
        vector = v_add(
            tuple([up_v[2], up_v[0], up_v[1]]),
            tuple([up_v[1], up_v[2], up_v[0]]),
        )
        offset = v_mul(v_norm(v_add(vector, up_v)), distance)
        return offset, up_v
    raise ValueError(f"Unknown camera view: {name}")


def offset_for_orbit(
    yaw_deg: float, up: str = "+Y", distance: float = 1000.0, elevation_deg: float = 15.0
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Offset for an orbit step: yaw around up, slight elevation above the equator."""
    up_v = _up_vector(up)
    forward, right = _horizontal_basis(up)
    yaw = math.radians(yaw_deg)
    elev = math.radians(elevation_deg)
    horizontal = v_add(v_mul(forward, math.cos(yaw)), v_mul(right, math.sin(yaw)))
    horizontal = v_norm(horizontal)
    direction = v_norm(
        v_add(v_mul(horizontal, math.cos(elev)), v_mul(up_v, math.sin(elev)))
    )
    return v_mul(direction, distance), up_v


def apply_view(camera: Any, name: str, up: str = "+Y") -> None:
    """Place ``camera`` for a named preset and ``reset_to_bounds``."""
    offset, view_up = offset_for_view(name, up=up)
    focal = tuple(camera.focal_point)
    camera.position = v_add(focal, offset)
    camera.view_up = view_up
    camera.reset_to_bounds()


def apply_orbit(
    camera: Any, yaw_deg: float, up: str = "+Y", elevation_deg: float = 15.0
) -> None:
    """Place ``camera`` for an orbit yaw and ``reset_to_bounds``."""
    offset, view_up = offset_for_orbit(yaw_deg, up=up, elevation_deg=elevation_deg)
    focal = tuple(camera.focal_point)
    camera.position = v_add(focal, offset)
    camera.view_up = view_up
    camera.reset_to_bounds()
