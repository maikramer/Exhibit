# SPDX-License-Identifier: GPL-3.0-or-later
"""Expanded camera_views coverage across presets, ups, orbit."""

from __future__ import annotations

import math

import pytest

from exhibit.camera_views import (
    PRESET_VIEWS,
    UP_DIRS,
    _horizontal_basis,
    _up_vector,
    apply_orbit,
    apply_view,
    offset_for_orbit,
    offset_for_view,
)
from exhibit.vector_math import v_mod


class _FakeCamera:
    def __init__(self, focal=(0.0, 0.0, 0.0)):
        self.focal_point = focal
        self.position = (0.0, 0.0, 0.0)
        self.view_up = (0.0, 1.0, 0.0)
        self.reset_calls = 0

    def reset_to_bounds(self):
        self.reset_calls += 1


@pytest.mark.parametrize("up", sorted(UP_DIRS.keys()))
def test_up_vector_matches_table(up: str):
    assert _up_vector(up) == UP_DIRS[up]


@pytest.mark.parametrize("bad", ["", "Y", "++Y", "up", "0", "+W", "-W"])
def test_up_vector_invalid(bad: str):
    with pytest.raises(ValueError, match="Invalid up direction"):
        _up_vector(bad)


@pytest.mark.parametrize("up", sorted(UP_DIRS.keys()))
def test_horizontal_basis_orthonormal(up: str):
    forward, right = _horizontal_basis(up)
    up_v = UP_DIRS[up]
    assert v_mod(forward) == pytest.approx(1.0, abs=1e-6)
    assert v_mod(right) == pytest.approx(1.0, abs=1e-6)
    # forward · right ≈ 0, both ⊥ up
    assert sum(a * b for a, b in zip(forward, right)) == pytest.approx(0.0, abs=1e-5)
    assert sum(a * b for a, b in zip(forward, up_v)) == pytest.approx(0.0, abs=1e-5)
    assert sum(a * b for a, b in zip(right, up_v)) == pytest.approx(0.0, abs=1e-5)


@pytest.mark.parametrize("name", PRESET_VIEWS)
@pytest.mark.parametrize("up", sorted(UP_DIRS.keys()))
@pytest.mark.parametrize("distance", [1.0, 10.0, 1000.0])
def test_offset_for_view_distance(name: str, up: str, distance: float):
    offset, view_up = offset_for_view(name, up=up, distance=distance)
    assert v_mod(offset) == pytest.approx(distance, rel=1e-5, abs=1e-6)
    assert v_mod(view_up) == pytest.approx(1.0, rel=1e-5, abs=1e-6)


@pytest.mark.parametrize("up", sorted(UP_DIRS.keys()))
def test_front_back_are_opposites(up: str):
    f, _ = offset_for_view("front", up=up, distance=100.0)
    b, _ = offset_for_view("back", up=up, distance=100.0)
    assert f == pytest.approx(tuple(-x for x in b), abs=1e-6)


@pytest.mark.parametrize("up", sorted(UP_DIRS.keys()))
def test_left_right_are_opposites(up: str):
    r, _ = offset_for_view("right", up=up, distance=50.0)
    l, _ = offset_for_view("left", up=up, distance=50.0)
    assert r == pytest.approx(tuple(-x for x in l), abs=1e-6)


@pytest.mark.parametrize("up", sorted(UP_DIRS.keys()))
def test_top_offset_along_up(up: str):
    offset, view_up = offset_for_view("top", up=up, distance=10.0)
    up_v = UP_DIRS[up]
    # offset should be parallel to up
    assert offset == pytest.approx(tuple(c * 10.0 for c in up_v), abs=1e-6)
    assert v_mod(view_up) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize(
    "bad",
    ["diagonal", "FRONT", "iso", "side", "bottom", "orbit", ""],
)
def test_unknown_view_raises(bad: str):
    with pytest.raises(ValueError, match="Unknown camera view"):
        offset_for_view(bad)


@pytest.mark.parametrize("yaw", [0.0, 45.0, 90.0, 180.0, 270.0, 359.0, -30.0])
@pytest.mark.parametrize("up", ["+Y", "+Z", "+X"])
@pytest.mark.parametrize("distance", [1.0, 100.0])
def test_orbit_distance(yaw: float, up: str, distance: float):
    offset, view_up = offset_for_orbit(yaw, up=up, distance=distance)
    assert v_mod(offset) == pytest.approx(distance, rel=1e-5, abs=1e-6)
    assert view_up == UP_DIRS[up]


@pytest.mark.parametrize("elev", [0.0, 15.0, 45.0, 89.0])
def test_orbit_elevation_affects_dot_with_up(elev: float):
    offset, _ = offset_for_orbit(0.0, up="+Y", distance=1.0, elevation_deg=elev)
    up = (0.0, 1.0, 0.0)
    # direction · up ≈ sin(elev)
    direction = offset  # unit length at distance=1
    assert sum(a * b for a, b in zip(direction, up)) == pytest.approx(
        math.sin(math.radians(elev)), abs=1e-5
    )


@pytest.mark.parametrize("name", PRESET_VIEWS)
def test_apply_view_sets_position_and_resets(name: str):
    cam = _FakeCamera(focal=(1.0, 2.0, 3.0))
    apply_view(cam, name, up="+Y")
    assert cam.reset_calls == 1
    assert cam.position != cam.focal_point


@pytest.mark.parametrize("yaw", [0.0, 90.0, 180.0])
def test_apply_orbit_sets_position(yaw: float):
    cam = _FakeCamera()
    apply_orbit(cam, yaw, up="+Y", elevation_deg=15.0)
    assert cam.reset_calls == 1
    assert v_mod(cam.position) == pytest.approx(1000.0, rel=1e-5)
