# SPDX-License-Identifier: GPL-3.0-or-later
"""Clickable 3D navigation cube overlay for camera view presets."""

from __future__ import annotations

import math
from gettext import gettext as _

from gi.repository import GObject, Gtk

# Face id → (outward normal, short label, viewer method name)
_FACES = (
    ((0.0, 0.0, 1.0), "F", "front_view"),
    ((0.0, 0.0, -1.0), "Bk", "back_view"),
    ((1.0, 0.0, 0.0), "R", "right_view"),
    ((-1.0, 0.0, 0.0), "L", "left_view"),
    ((0.0, 1.0, 0.0), "T", "top_view"),
    ((0.0, -1.0, 0.0), "Bo", "bottom_view"),
)

_CUBE_HALF = 0.55


def _v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _v_cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _v_norm(v):
    length = math.sqrt(_v_dot(v, v))
    if length < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def _face_corners(normal):
    """Four corners of a cube face with the given outward normal."""
    nx, ny, nz = normal
    if abs(nx) > 0.5:
        u, v = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
        c = (math.copysign(_CUBE_HALF, nx), 0.0, 0.0)
    elif abs(ny) > 0.5:
        u, v = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
        c = (0.0, math.copysign(_CUBE_HALF, ny), 0.0)
    else:
        u, v = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        c = (0.0, 0.0, math.copysign(_CUBE_HALF, nz))
    h = _CUBE_HALF
    return (
        (c[0] + u[0] * h + v[0] * h, c[1] + u[1] * h + v[1] * h, c[2] + u[2] * h + v[2] * h),
        (c[0] - u[0] * h + v[0] * h, c[1] - u[1] * h + v[1] * h, c[2] - u[2] * h + v[2] * h),
        (c[0] - u[0] * h - v[0] * h, c[1] - u[1] * h - v[1] * h, c[2] - u[2] * h - v[2] * h),
        (c[0] + u[0] * h - v[0] * h, c[1] + u[1] * h - v[1] * h, c[2] + u[2] * h - v[2] * h),
    )


class NavCube(Gtk.DrawingArea):
    """Small projected cube; click a face to jump to that camera preset."""

    __gtype_name__ = "ExhibitNavCube"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_content_width(96)
        self.set_content_height(96)
        self.set_size_request(96, 96)
        self.set_draw_func(self._on_draw)
        self.add_css_class("nav-cube")
        self.set_tooltip_text(_("Click a face to set the camera view"))
        self._forward = (0.0, 0.0, 1.0)
        self._up = (0.0, 1.0, 0.0)
        self._viewer = None
        self._hover_face = -1

        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

    def set_viewer(self, viewer) -> None:
        self._viewer = viewer

    def sync_from_camera_state(self, state) -> None:
        """Update orientation from ``(pos×3, focal×3, up×3)`` camera state."""
        if state is None or len(state) < 9:
            return
        pos = (float(state[0]), float(state[1]), float(state[2]))
        focal = (float(state[3]), float(state[4]), float(state[5]))
        up = (float(state[6]), float(state[7]), float(state[8]))
        forward = _v_norm(_v_sub(focal, pos))
        self._forward = forward
        self._up = _v_norm(up)
        self.queue_draw()

    def _basis(self):
        # Camera looks along +forward; project onto screen with +up.
        fwd = self._forward
        up = self._up
        right = _v_norm(_v_cross(fwd, up))
        # Re-orthogonalize up against right/fwd drift.
        up = _v_norm(_v_cross(right, fwd))
        return right, up, fwd

    def _project(self, p, right, up, fwd, cx, cy, scale):
        # View from outside looking toward cube center (opposite of camera fwd).
        x = _v_dot(p, right) * scale + cx
        y = -_v_dot(p, up) * scale + cy
        depth = _v_dot(p, fwd)
        return x, y, depth

    def _visible_faces(self):
        right, up, fwd = self._basis()
        # Faces whose outward normal points toward the camera (against view).
        view_dir = (-fwd[0], -fwd[1], -fwd[2])
        out = []
        for i, (normal, label, method) in enumerate(_FACES):
            facing = _v_dot(normal, view_dir)
            if facing <= 0.05:
                continue
            corners = _face_corners(normal)
            out.append((facing, i, normal, label, method, corners))
        out.sort(key=lambda item: item[0])  # far → near for paint order
        return out, right, up, fwd

    def _on_draw(self, _area, cr, width, height):
        cx, cy = width * 0.5, height * 0.5
        scale = min(width, height) * 0.42
        faces, right, up, fwd = self._visible_faces()

        # Soft disc behind the cube.
        cr.set_source_rgba(0.12, 0.12, 0.14, 0.55)
        cr.arc(cx, cy, min(width, height) * 0.48, 0, 2 * math.pi)
        cr.fill()

        for _facing, idx, _n, label, _method, corners in faces:
            pts = [
                self._project(c, right, up, fwd, cx, cy, scale) for c in corners
            ]
            cr.new_path()
            cr.move_to(pts[0][0], pts[0][1])
            for x, y, _d in pts[1:]:
                cr.line_to(x, y)
            cr.close_path()
            if idx == self._hover_face:
                cr.set_source_rgba(0.35, 0.55, 0.95, 0.85)
            else:
                cr.set_source_rgba(0.22, 0.24, 0.28, 0.9)
            cr.fill_preserve()
            cr.set_source_rgba(0.85, 0.88, 0.92, 0.95)
            cr.set_line_width(1.25)
            cr.stroke()

            mx = sum(p[0] for p in pts) / 4.0
            my = sum(p[1] for p in pts) / 4.0
            cr.set_source_rgba(0.95, 0.96, 0.98, 1.0)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(11 if len(label) == 1 else 9)
            extents = cr.text_extents(label)
            cr.move_to(mx - extents.width / 2, my + extents.height / 2)
            cr.show_text(label)

    def _face_at(self, x: float, y: float) -> int:
        width = max(self.get_width(), 1)
        height = max(self.get_height(), 1)
        cx, cy = width * 0.5, height * 0.5
        scale = min(width, height) * 0.42
        faces, right, up, fwd = self._visible_faces()
        # Nearest (most facing) face whose projected quad contains the point.
        for _facing, idx, _n, _label, _method, corners in reversed(faces):
            pts = [
                self._project(c, right, up, fwd, cx, cy, scale)[:2]
                for c in corners
            ]
            if _point_in_quad(x, y, pts):
                return idx
        return -1

    def _on_motion(self, _ctrl, x, y):
        face = self._face_at(x, y)
        if face != self._hover_face:
            self._hover_face = face
            self.queue_draw()

    def _on_leave(self, *_args):
        if self._hover_face != -1:
            self._hover_face = -1
            self.queue_draw()

    def _on_click(self, _gesture, _n_press, x, y):
        face = self._face_at(x, y)
        if face < 0 or self._viewer is None:
            return
        method_name = _FACES[face][2]
        method = getattr(self._viewer, method_name, None)
        if callable(method):
            method()


def _point_in_quad(x, y, pts) -> bool:
    """Convex quad containment via cross-product winding."""
    if len(pts) != 4:
        return False
    sign = None
    for i in range(4):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % 4]
        cross = (x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)
        if abs(cross) < 1e-9:
            continue
        s = cross > 0
        if sign is None:
            sign = s
        elif s != sign:
            return False
    return sign is not None


GObject.type_ensure(NavCube)
