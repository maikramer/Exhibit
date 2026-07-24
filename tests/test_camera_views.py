# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from exhibit.camera_views import (
    PRESET_VIEWS,
    apply_orbit,
    apply_view,
    offset_for_orbit,
    offset_for_view,
)
from exhibit.vector_math import v_mod


class _FakeCamera:
    def __init__(self):
        self.focal_point = (0.0, 0.0, 0.0)
        self.position = (0.0, 0.0, 0.0)
        self.view_up = (0.0, 1.0, 0.0)
        self.reset_calls = 0

    def reset_to_bounds(self):
        self.reset_calls += 1


@pytest.mark.parametrize("name", PRESET_VIEWS)
def test_offset_for_view_unit_distance(name: str):
    offset, view_up = offset_for_view(name, up="+Y", distance=1000.0)
    assert v_mod(offset) == pytest.approx(1000.0, rel=1e-6)
    assert v_mod(view_up) == pytest.approx(1.0, rel=1e-6)


def test_offset_unknown_raises():
    with pytest.raises(ValueError, match="Unknown camera view"):
        offset_for_view("diagonal")


def test_orbit_yaw_changes_offset():
    a, _ = offset_for_orbit(0.0, distance=10.0)
    b, _ = offset_for_orbit(90.0, distance=10.0)
    assert a != b
    assert v_mod(a) == pytest.approx(10.0, rel=1e-6)


def test_apply_view_and_orbit_reset():
    cam = _FakeCamera()
    apply_view(cam, "front")
    assert cam.reset_calls == 1
    assert cam.position != cam.focal_point
    apply_orbit(cam, 45.0)
    assert cam.reset_calls == 2
