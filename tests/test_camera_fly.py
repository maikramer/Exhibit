# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for FPS free-fly camera math."""

from __future__ import annotations

import math

import pytest

from exhibit.camera_fly import (
    fly_axis_step,
    fly_look,
    fly_look_velocity_step,
    fly_move,
    fly_speed_for_distance,
    fly_velocity_step,
    pack_state,
    unpack_state,
)
from exhibit.vector_math import v_dot, v_mod, v_norm, v_sub


def _front_state(dist: float = 10.0):
    # Camera at +Z looking at origin, +Y up.
    return pack_state((0.0, 0.0, dist), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def test_fly_move_forward_reduces_distance_to_origin():
    state = _front_state(10.0)
    moved = fly_move(state, move_fwd=1.0, speed=2.0, world_up=(0.0, 1.0, 0.0))
    pos, focal, _up = unpack_state(moved)
    assert v_mod(pos) < 10.0
    # Focal moves with camera (look distance preserved).
    assert v_mod(v_sub(focal, pos)) == pytest.approx(10.0)


def test_fly_move_strafe_changes_x():
    state = _front_state(10.0)
    moved = fly_move(state, move_right=1.0, speed=3.0)
    pos, _f, _u = unpack_state(moved)
    assert pos[0] > 0.0


def test_fly_move_up_with_world_up():
    state = _front_state(10.0)
    moved = fly_move(state, move_up=1.0, speed=4.0)
    pos, _f, _u = unpack_state(moved)
    assert pos[1] == pytest.approx(4.0)


def test_fly_look_yaw_rotates_around_up():
    state = _front_state(10.0)
    # Positive dx → yaw left/right; forward should leave pure -Z.
    looked = fly_look(state, dx=90.0, dy=0.0, sens_deg=1.0)
    pos, focal, up = unpack_state(looked)
    forward = v_norm(v_sub(focal, pos))
    assert abs(forward[0]) > 0.5
    assert v_mod(v_sub(focal, pos)) == pytest.approx(10.0)
    assert up[1] > 0.5


def test_fly_look_pitch_clamped_near_pole():
    state = _front_state(10.0)
    looked = state
    for _ in range(40):
        looked = fly_look(looked, dx=0.0, dy=-50.0, sens_deg=1.0)
    pos, focal, _up = unpack_state(looked)
    forward = v_norm(v_sub(focal, pos))
    # Must not flip past world up.
    assert abs(v_dot(forward, (0.0, 1.0, 0.0))) < math.cos(math.radians(4.0))


def test_fly_speed_scales_with_distance():
    assert fly_speed_for_distance(100.0) > fly_speed_for_distance(1.0)
    assert fly_speed_for_distance(0.0) > 0.0


def test_fly_axis_accel_ramps_toward_wish():
    v = 0.0
    for _ in range(5):
        v = fly_axis_step(v, 1.0, accel=3.0, drag=5.0, dt=1.0 / 60.0)
    assert 0.0 < v < 1.0
    for _ in range(200):
        v = fly_axis_step(v, 1.0, accel=3.0, drag=5.0, dt=1.0 / 60.0)
    assert v == pytest.approx(1.0, abs=1e-3)


def test_fly_axis_drag_coasts_to_zero():
    v = 1.0
    for _ in range(120):
        v = fly_axis_step(v, 0.0, accel=3.0, drag=5.0, dt=1.0 / 60.0)
    assert v == 0.0


def test_fly_velocity_step_tracks_wish_axes():
    vel = (0.0, 0.0, 0.0)
    for _ in range(30):
        vel = fly_velocity_step(vel, (1.0, -1.0, 0.0), dt=1.0 / 60.0)
    assert vel[0] > 0.5
    assert vel[1] < -0.5
    assert vel[2] == 0.0


def test_fly_look_velocity_decays():
    lx, ly = fly_look_velocity_step((10.0, -8.0), drag=10.0, dt=1.0 / 60.0)
    assert abs(lx) < 10.0
    assert abs(ly) < 8.0
    for _ in range(120):
        lx, ly = fly_look_velocity_step((lx, ly), drag=10.0, dt=1.0 / 60.0)
    assert lx == 0.0
    assert ly == 0.0
