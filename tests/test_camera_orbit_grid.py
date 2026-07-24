# SPDX-License-Identifier: GPL-3.0-or-later
"""Dense orbit grid: yaw × elevation × up × distance."""

from __future__ import annotations

import math

import pytest

from exhibit.camera_views import UP_DIRS, offset_for_orbit, offset_for_view
from exhibit.vector_math import v_mod


YAWS = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
ELEVS = [0, 10, 15, 30, 45]
UPS = ["+Y", "-Y", "+Z", "-Z", "+X", "-X"]
DISTS = [1.0, 50.0]


@pytest.mark.parametrize("yaw", YAWS)
@pytest.mark.parametrize("elev", ELEVS)
@pytest.mark.parametrize("up", UPS[:3])  # keep total ~180
@pytest.mark.parametrize("distance", DISTS)
def test_orbit_grid_unit_length(yaw, elev, up, distance):
    offset, view_up = offset_for_orbit(
        float(yaw), up=up, distance=distance, elevation_deg=float(elev)
    )
    assert v_mod(offset) == pytest.approx(distance, rel=1e-5, abs=1e-6)
    assert view_up == UP_DIRS[up]
    # elevation relationship vs up axis
    direction = tuple(c / distance for c in offset)
    up_v = UP_DIRS[up]
    dot = sum(a * b for a, b in zip(direction, up_v))
    assert dot == pytest.approx(math.sin(math.radians(elev)), abs=1e-4)


@pytest.mark.parametrize("name", ["front", "right", "back", "left", "top", "isometric"])
@pytest.mark.parametrize("up", UPS)
def test_presets_finite(name, up):
    offset, view_up = offset_for_view(name, up=up, distance=10.0)
    assert all(math.isfinite(c) for c in offset)
    assert all(math.isfinite(c) for c in view_up)
