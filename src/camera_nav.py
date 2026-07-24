# SPDX-License-Identifier: GPL-3.0-or-later
"""Cursor-aware camera navigation helpers (Blender / F3D-style)."""

from __future__ import annotations

import math
from typing import Callable

from .vector_math import p_dist, v_add, v_cross, v_dot, v_mul, v_norm, v_sub

Vec3 = tuple[float, float, float]


def gtk_to_display(x: float, y: float, height: float, scale: float = 1.0) -> tuple[float, float]:
    """GTK top-left widget coords → VTK/F3D bottom-left display coords."""
    return float(x) * scale, (float(height) - float(y)) * scale


def rotate_around_axis(point: Vec3, pivot: Vec3, axis: Vec3, angle_rad: float) -> Vec3:
    """Rodrigues rotation of ``point`` around ``axis`` through ``pivot``."""
    axis_n = v_norm(axis)
    if v_dot(axis_n, axis_n) < 1e-18:
        return point
    rel = v_sub(point, pivot)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return v_add(
        pivot,
        v_add(
            v_mul(rel, cos_a),
            v_add(
                v_mul(v_cross(axis_n, rel), sin_a),
                v_mul(axis_n, v_dot(axis_n, rel) * (1.0 - cos_a)),
            ),
        ),
    )


def pivot_camera_to_point(
    position: Vec3, focal: Vec3, pivot: Vec3, *, keep_camera_plane: bool = True
) -> tuple[Vec3, Vec3]:
    """
    Move focal to ``pivot`` and slide the camera (F3D middle-click recenter).

    With ``keep_camera_plane``, the camera stays on its original view plane
    (translation orthogonal to the view direction).
    """
    foc_v = v_sub(pivot, focal)
    pos_v = foc_v
    if keep_camera_plane:
        view = v_sub(focal, position)
        view_len2 = v_dot(view, view)
        if view_len2 > 1e-18:
            # Project foc_v onto view; remove that component from the camera shift.
            proj = v_mul(view, v_dot(foc_v, view) / view_len2)
            pos_v = v_sub(foc_v, proj)
    return v_add(position, pos_v), v_add(focal, foc_v)


def clamp_dolly_factor(factor: float, *, lo: float = 0.5, hi: float = 2.0) -> float:
    """Keep per-event dolly factors away from 0 / negatives / explosion."""
    if factor != factor or abs(factor) == float("inf"):  # NaN / inf
        return 1.0
    return max(lo, min(hi, float(factor)))


def clamp_scroll_delta(
    dx: float, dy: float, *, touchpad: bool
) -> tuple[float, float]:
    """Limit scroll deltas so one touchpad event cannot fling the camera."""
    limit = 8.0 if touchpad else 3.0
    return (
        max(-limit, min(limit, float(dx))),
        max(-limit, min(limit, float(dy))),
    )


def is_finite_vec3(point: Vec3) -> bool:
    return all(v == v and abs(v) != float("inf") for v in point)


def is_sane_pivot(
    pivot: Vec3,
    position: Vec3,
    focal: Vec3,
    *,
    max_distance_factor: float = 50.0,
) -> bool:
    """
    Reject unproject failures / runaway pivots.

    F3D ``get_world_from_display`` returns ``(0,0,0)`` when homogeneous w is
    tiny; orbiting that from a distant camera sends the view to infinity.
    """
    if not is_finite_vec3(pivot):
        return False
    base = max(p_dist(position, focal), 1e-3)
    if p_dist(position, pivot) > base * max_distance_factor:
        return False
    if p_dist(focal, pivot) > base * max_distance_factor:
        return False
    return True


def dolly_to_cursor(
    position: Vec3,
    focal: Vec3,
    factor: float,
    cursor_world: Vec3,
) -> tuple[Vec3, Vec3]:
    """
    Zoom toward ``cursor_world`` (F3D ``DollyToPosition``).

    Temporarily aims at the cursor, dollies along the view, then restores the
    original focal by translating it with the camera motion.
    """
    factor = clamp_dolly_factor(factor)
    if abs(factor - 1.0) < 1e-12:
        return position, focal

    old_pos = position
    old_foc = focal
    # Aim at cursor, then move camera along (cursor - pos) by dolly factor.
    # Dolly factor > 1 moves toward focal; camera.dolly(f) moves position to
    # focal + (pos-focal)/f in VTK. Equivalent: pos' = foc + (pos-foc)/factor
    # when foc is the aim point.
    aim = cursor_world
    offset = v_sub(old_pos, aim)
    new_pos = v_add(aim, v_mul(offset, 1.0 / factor))
    if not is_finite_vec3(new_pos):
        return position, focal
    delta = v_sub(new_pos, old_pos)
    new_foc = v_add(old_foc, delta)
    return new_pos, new_foc


def orbit_rig_around_pivot(
    position: Vec3,
    focal: Vec3,
    pivot: Vec3,
    up: Vec3,
    azimuth_deg: float,
    elevation_deg: float,
    *,
    gimbal_ok: Callable[[Vec3, Vec3], bool] | None = None,
) -> tuple[Vec3, Vec3]:
    """
    Rotate camera position and focal around ``pivot`` (turntable).

    Azimuth uses world ``up``. Elevation uses camera-right through the pivot.
    """
    pos, foc = position, focal
    if abs(azimuth_deg) > 1e-12:
        az = math.radians(azimuth_deg)
        pos = rotate_around_axis(pos, pivot, up, az)
        foc = rotate_around_axis(foc, pivot, up, az)

    if abs(elevation_deg) > 1e-12:
        view = v_sub(foc, pos)
        right = v_norm(v_cross(view, up))
        if v_dot(right, right) > 1e-12:
            if gimbal_ok is None or gimbal_ok(pos, foc):
                el = math.radians(elevation_deg)
                pos = rotate_around_axis(pos, pivot, right, el)
                foc = rotate_around_axis(foc, pivot, right, el)

    return pos, foc


def pan_scale_for_distance(distance: float, width: float) -> float:
    """Pixel → world pan scale; grows with camera distance."""
    return 0.0000001 * max(width, 1.0) + 0.001 * max(distance, 1e-6)


def depth_distance(position: Vec3, point: Vec3) -> float:
    return p_dist(position, point)


def axis_delta(value: float, *, invert: bool = False, sensitivity: float = 1.0) -> float:
    """Apply optional axis inversion and sensitivity to a pointer delta."""
    signed = -value if invert else value
    return signed * float(sensitivity)


def clamp_sensitivity(value: float, *, lo: float = 0.25, hi: float = 4.0) -> float:
    return max(lo, min(hi, float(value)))


# Defaults mirrored by WindowSettings / gschema.
NAV_SETTING_DEFAULTS = {
    "nav-invert-x": False,
    "nav-invert-y": False,
    "nav-zoom-to-cursor": True,
    # Classic Exhibit: orbit the view/focal center (no screen drift).
    "nav-orbit-around-cursor": False,
    "nav-touchpad-orbit": True,
    "nav-mmb-click-pivot": True,
    "nav-orbit-sensitivity": 1.0,
    "nav-zoom-sensitivity": 1.0,
    "nav-pan-sensitivity": 1.0,
}
