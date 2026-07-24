# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import math

import pytest

from exhibit.camera_nav import (
    axis_delta,
    clamp_dolly_factor,
    clamp_scroll_delta,
    clamp_sensitivity,
    dolly_to_cursor,
    gtk_to_display,
    is_sane_pivot,
    orbit_rig_around_pivot,
    pivot_camera_to_point,
    rotate_around_axis,
)
from exhibit.vector_math import p_dist, v_dot, v_sub


def test_gtk_to_display_flips_y():
    assert gtk_to_display(10, 20, height=100, scale=1) == (10.0, 80.0)
    assert gtk_to_display(10, 20, height=100, scale=2) == (20.0, 160.0)


def test_rotate_around_axis_90_deg():
    out = rotate_around_axis((1, 0, 0), (0, 0, 0), (0, 0, 1), math.pi / 2)
    assert out[0] == pytest.approx(0.0, abs=1e-9)
    assert out[1] == pytest.approx(1.0, abs=1e-9)
    assert out[2] == pytest.approx(0.0, abs=1e-9)


def test_pivot_camera_keeps_view_plane():
    pos = (0.0, 0.0, 10.0)
    foc = (0.0, 0.0, 0.0)
    pivot = (2.0, 0.0, 0.0)
    new_pos, new_foc = pivot_camera_to_point(pos, foc, pivot, keep_camera_plane=True)
    assert new_foc == pytest.approx(pivot)
    # Camera slides on its plane (z stays 10); looks toward new focal.
    assert new_pos[2] == pytest.approx(10.0)
    assert new_pos[0] == pytest.approx(2.0)


def test_dolly_to_cursor_moves_toward_cursor():
    pos = (0.0, 0.0, 10.0)
    foc = (0.0, 0.0, 0.0)
    cursor = (3.0, 0.0, 0.0)
    new_pos, new_foc = dolly_to_cursor(pos, foc, factor=2.0, cursor_world=cursor)
    # Closer to cursor aim point.
    assert p_dist(new_pos, cursor) < p_dist(pos, cursor)
    # Focal translates with camera.
    assert v_sub(new_foc, foc) == pytest.approx(v_sub(new_pos, pos))


def test_dolly_clamps_extreme_factor():
    pos = (0.0, 0.0, 10.0)
    foc = (0.0, 0.0, 0.0)
    cursor = (0.0, 0.0, 0.0)
    # Factor 0 / negative would previously explode via 1/factor.
    new_pos, new_foc = dolly_to_cursor(pos, foc, factor=0.0, cursor_world=cursor)
    assert all(v == v and abs(v) != float("inf") for v in new_pos)
    assert all(v == v and abs(v) != float("inf") for v in new_foc)
    assert clamp_dolly_factor(0.0) == 0.5
    assert clamp_dolly_factor(10.0) == 2.0
    assert clamp_dolly_factor(float("nan")) == 1.0


def test_orbit_around_pivot_keeps_pivot_distance():
    pos = (0.0, 0.0, 10.0)
    foc = (0.0, 0.0, 0.0)
    pivot = (1.0, 0.0, 0.0)
    up = (0.0, 1.0, 0.0)
    new_pos, new_foc = orbit_rig_around_pivot(pos, foc, pivot, up, 90.0, 0.0)
    assert p_dist(new_pos, pivot) == pytest.approx(p_dist(pos, pivot))
    assert p_dist(new_foc, pivot) == pytest.approx(p_dist(foc, pivot))
    # View direction still roughly toward scene (pos -> foc not flipped oddly).
    assert v_dot(v_sub(new_foc, new_pos), v_sub(foc, pos)) != 0


def test_classic_orbit_around_focal_keeps_focal_fixed():
    """View-center orbit must not slide the focal point (no model drift)."""
    pos = (0.0, 0.0, 10.0)
    foc = (0.0, 0.0, 0.0)
    up = (0.0, 1.0, 0.0)
    new_pos, new_foc = orbit_rig_around_pivot(pos, foc, foc, up, 45.0, 20.0)
    assert new_foc == pytest.approx(foc)
    assert p_dist(new_pos, foc) == pytest.approx(p_dist(pos, foc))


def test_is_sane_pivot_rejects_runaway_and_nan():
    pos = (0.0, 0.0, 10.0)
    foc = (0.0, 0.0, 0.0)
    assert is_sane_pivot((1.0, 0.0, 0.0), pos, foc)
    assert not is_sane_pivot((1e9, 0.0, 0.0), pos, foc)
    assert not is_sane_pivot((float("nan"), 0.0, 0.0), pos, foc)


def test_clamp_scroll_delta_touchpad_vs_wheel():
    dx, dy = clamp_scroll_delta(100.0, -100.0, touchpad=True)
    assert dx == 8.0
    assert dy == -8.0
    dx, dy = clamp_scroll_delta(100.0, -100.0, touchpad=False)
    assert dx == 3.0
    assert dy == -3.0


def test_axis_delta_and_sensitivity():
    assert axis_delta(2.0, invert=False, sensitivity=1.0) == 2.0
    assert axis_delta(2.0, invert=True, sensitivity=1.0) == -2.0
    assert axis_delta(2.0, invert=False, sensitivity=0.5) == 1.0
    assert clamp_sensitivity(0.01) == 0.25
    assert clamp_sensitivity(99.0) == 4.0
