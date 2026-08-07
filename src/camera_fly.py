# SPDX-License-Identifier: GPL-3.0-or-later
"""FPS-style free-fly camera math (WASD + mouse look)."""

from __future__ import annotations

import math

from .camera_nav import rotate_around_axis
from .vector_math import v_add, v_cross, v_dot, v_mod, v_mul, v_norm, v_sub

Vec3 = tuple[float, float, float]
CamState = tuple[float, ...]  # pos×3, focal×3, up×3
_ORIGIN: Vec3 = (0.0, 0.0, 0.0)

# Tuned for easy control: slower base speed, soft accel, coasting drag.
FLY_LOOK_SENS_DEG = 0.07
FLY_LOOK_INERTIA = 0.45  # fraction of mouse delta kept as look velocity
FLY_LOOK_DRAG = 10.0  # 1/s — look velocity decay
FLY_SPEED_FRACTION = 0.012
FLY_MOVE_ACCEL = 3.2  # 1/s — ramp toward wish
FLY_MOVE_DRAG = 5.5  # 1/s — coast / brake when keys released
FLY_VEL_EPS = 1e-4
FLY_DT = 1.0 / 60.0


def unpack_state(state) -> tuple[Vec3, Vec3, Vec3] | None:
    if state is None or len(state) < 9:
        return None
    pos = (float(state[0]), float(state[1]), float(state[2]))
    focal = (float(state[3]), float(state[4]), float(state[5]))
    up = (float(state[6]), float(state[7]), float(state[8]))
    return pos, focal, up


def pack_state(pos: Vec3, focal: Vec3, up: Vec3) -> CamState:
    return (*pos, *focal, *up)


def _rotate_dir(direction: Vec3, axis: Vec3, angle_deg: float) -> Vec3:
    return v_norm(
        rotate_around_axis(
            direction, _ORIGIN, axis, math.radians(float(angle_deg))
        )
    )


def fly_basis(pos: Vec3, focal: Vec3, world_up: Vec3) -> tuple[Vec3, Vec3, Vec3]:
    """Return (forward, right, up) for FPS movement; up stays near world_up."""
    forward = v_norm(v_sub(focal, pos))
    wu = v_norm(world_up)
    right = v_cross(forward, wu)
    if v_mod(right) < 1e-8:
        right = v_cross(forward, (0.0, 0.0, 1.0))
        if v_mod(right) < 1e-8:
            right = (1.0, 0.0, 0.0)
    right = v_norm(right)
    up = v_norm(v_cross(right, forward))
    return forward, right, up


def fly_axis_step(
    velocity: float,
    wish: float,
    *,
    accel: float = FLY_MOVE_ACCEL,
    drag: float = FLY_MOVE_DRAG,
    dt: float = FLY_DT,
) -> float:
    """Ease one axis toward wish (-1..1); drag when wish is zero (coasting)."""
    v = float(velocity)
    w = max(-1.0, min(1.0, float(wish)))
    rate = float(accel) if abs(w) > 1e-6 else float(drag)
    if rate <= 0.0 or dt <= 0.0:
        return w if abs(w) > 1e-6 else 0.0
    v = v + (w - v) * (1.0 - math.exp(-rate * dt))
    if abs(v) < FLY_VEL_EPS:
        return 0.0
    return v


def fly_velocity_step(
    velocity: Vec3,
    wish: Vec3,
    *,
    accel: float = FLY_MOVE_ACCEL,
    drag: float = FLY_MOVE_DRAG,
    dt: float = FLY_DT,
) -> Vec3:
    """Integrate local (fwd, right, up) wish-space velocity with accel/drag."""
    return (
        fly_axis_step(velocity[0], wish[0], accel=accel, drag=drag, dt=dt),
        fly_axis_step(velocity[1], wish[1], accel=accel, drag=drag, dt=dt),
        fly_axis_step(velocity[2], wish[2], accel=accel, drag=drag, dt=dt),
    )


def fly_look_velocity_step(
    look_vel: tuple[float, float],
    *,
    drag: float = FLY_LOOK_DRAG,
    dt: float = FLY_DT,
) -> tuple[float, float]:
    """Decay mouse-look momentum (pixels of residual motion)."""
    if drag <= 0.0 or dt <= 0.0:
        return (0.0, 0.0)
    factor = math.exp(-float(drag) * dt)
    lx = float(look_vel[0]) * factor
    ly = float(look_vel[1]) * factor
    if abs(lx) < FLY_VEL_EPS:
        lx = 0.0
    if abs(ly) < FLY_VEL_EPS:
        ly = 0.0
    return (lx, ly)


def fly_look(
    state: CamState,
    dx: float,
    dy: float,
    *,
    world_up: Vec3 = (0.0, 1.0, 0.0),
    sens_deg: float = FLY_LOOK_SENS_DEG,
    min_pitch_deg: float = 5.0,
) -> CamState | None:
    """Yaw (dx) around world up, pitch (dy) around camera right. Keeps focus distance."""
    unpacked = unpack_state(state)
    if unpacked is None:
        return None
    pos, focal, _up = unpacked
    offset = v_sub(focal, pos)
    dist = v_mod(offset)
    if dist < 1e-9:
        dist = 1.0
    forward = v_norm(offset)
    wu = v_norm(world_up)

    yaw = -float(dx) * sens_deg
    if abs(yaw) > 1e-9:
        forward = _rotate_dir(forward, wu, yaw)

    right = v_cross(forward, wu)
    if v_mod(right) < 1e-8:
        return pack_state(pos, v_add(pos, v_mul(forward, dist)), wu)
    right = v_norm(right)
    pitch = -float(dy) * sens_deg
    if abs(pitch) > 1e-9:
        pitched = _rotate_dir(forward, right, pitch)
        dot = abs(v_dot(pitched, wu))
        limit = math.cos(math.radians(min_pitch_deg))
        if dot <= limit:
            forward = pitched
            right = v_norm(v_cross(forward, wu))

    cam_up = v_norm(v_cross(right, forward))
    if v_mod(cam_up) < 1e-8:
        cam_up = wu
    if v_dot(cam_up, wu) < 0:
        cam_up = v_mul(cam_up, -1.0)
    return pack_state(pos, v_add(pos, v_mul(forward, dist)), cam_up)


def fly_move(
    state: CamState,
    *,
    move_fwd: float = 0.0,
    move_right: float = 0.0,
    move_up: float = 0.0,
    speed: float,
    world_up: Vec3 = (0.0, 1.0, 0.0),
) -> CamState | None:
    """Translate position + focal together (strafe / dolly / elevate)."""
    unpacked = unpack_state(state)
    if unpacked is None:
        return None
    pos, focal, up = unpacked
    forward, right, _cam_up = fly_basis(pos, focal, world_up)
    wu = v_norm(world_up)
    delta = v_add(
        v_add(v_mul(forward, move_fwd * speed), v_mul(right, move_right * speed)),
        v_mul(wu, move_up * speed),
    )
    if v_mod(delta) < 1e-12:
        return pack_state(pos, focal, up)
    return pack_state(v_add(pos, delta), v_add(focal, delta), up)


def fly_speed_for_distance(
    distance: float, *, fraction: float = FLY_SPEED_FRACTION
) -> float:
    """Per-tick step grows with camera distance so fly works on any scale."""
    d = abs(float(distance))
    if d < 1e-6:
        d = 1.0
    return max(0.0008, d * fraction)
