# viewer_tab.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Gdk, GLib, Gtk

from ..camera_fly import (
    FLY_DT,
    FLY_LOOK_INERTIA,
    FLY_LOOK_SENS_DEG,
    fly_look,
    fly_look_velocity_step,
    fly_move,
    fly_speed_for_distance,
    fly_velocity_step,
    unpack_state,
)
from ..camera_views import UP_DIRS
from ..vector_math import v_mod, v_sub
from .f3d_viewer import F3DViewer
from .nav_cube import NavCube

_FLY_KEYVALS = {
    Gdk.KEY_w: "w",
    Gdk.KEY_W: "w",
    Gdk.KEY_a: "a",
    Gdk.KEY_A: "a",
    Gdk.KEY_s: "s",
    Gdk.KEY_S: "s",
    Gdk.KEY_d: "d",
    Gdk.KEY_D: "d",
    Gdk.KEY_Shift_L: "shift",
    Gdk.KEY_Shift_R: "shift",
}


class ViewerTab(Gtk.Overlay):
    """One document page: Exb-backed viewer + optional stats HUD."""

    def __init__(self, viewer: F3DViewer | None = None):
        super().__init__()
        self.filepath = ""
        self.file_name = ""
        self.mesh_stats = None
        self.armature_xray_restore = None
        self.depth_opacity_restore = None
        self.depth_scivis_restore = None
        self.loaded = False
        # Disk mtime of the version currently shown in the viewer.
        self.loaded_mtime = 0.0
        # Last disk mtime we already reacted to (mark / prompt / reload).
        self.seen_disk_mtime = 0.0
        self.externally_modified = False
        self._reload_dialog_open = False
        # In-flight warm load holder (cancelled on tab close / replace load).
        self._warm_load_holder = None
        self._prepared_holder = None
        self._free_fly_camera_restore = None
        self._free_fly_interactive_restore = True
        self._free_fly_block = False
        self._fly_keys: set[str] = set()
        self._fly_tick_id = 0
        self._fly_look_active = False
        self._fly_last_xy: tuple[float, float] | None = None
        self._fly_vel = (0.0, 0.0, 0.0)  # fwd, right, up (-1..1)
        self._fly_look_vel = (0.0, 0.0)
        self._fly_pending_look = (0.0, 0.0)  # mouse dx/dy queued for tick
        self._fly_last_frame_us = 0
        self._fly_cube_sync_skip = 0
        self._fly_key_ctrl = None
        self._fly_motion = None
        self._fly_click = None

        if viewer is not None:
            self.viewer = viewer
        else:
            self.viewer = F3DViewer()
        self.engine = self.viewer.engine
        self.viewer.add_css_class("f3d-render")
        self.viewer.set_hexpand(True)
        self.viewer.set_vexpand(True)

        # Bridge mode wraps a template Exb.View that must not live inside the Box.
        if getattr(self.viewer, "_bridge", False):
            view = self.viewer.get_view()
            view.set_hexpand(True)
            view.set_vexpand(True)
            self.set_child(view)
        else:
            self.set_child(self.viewer)

        self.stats_overlay_label = Gtk.Label(
            visible=False,
            halign=Gtk.Align.START,
            valign=Gtk.Align.END,
            margin_start=16,
            margin_bottom=16,
            xalign=0,
            selectable=True,
        )
        self.stats_overlay_label.add_css_class("stats-overlay")
        self.add_overlay(self.stats_overlay_label)

        # Cube + Fly icon share one chrome box (header inset applies here).
        self.nav_chrome = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            halign=Gtk.Align.END,
            valign=Gtk.Align.START,
            margin_top=52,
            margin_end=12,
            visible=True,
        )
        self.nav_chrome.add_css_class("nav-chrome")
        self.nav_chrome.set_can_target(True)

        self.nav_cube = NavCube(halign=Gtk.Align.CENTER)
        self.nav_cube.set_viewer(self.viewer)
        self.nav_chrome.append(self.nav_cube)

        self.free_fly_button = Gtk.ToggleButton()
        self.free_fly_button.set_icon_name("airplane-mode-symbolic")
        self.free_fly_button.set_halign(Gtk.Align.CENTER)
        self.free_fly_button.set_valign(Gtk.Align.CENTER)
        self.free_fly_button.set_focus_on_click(False)
        self.free_fly_button.set_has_frame(False)
        self.free_fly_button.add_css_class("flat")
        self.free_fly_button.add_css_class("circular")
        self.free_fly_button.add_css_class("free-fly-button")
        self.free_fly_button.set_tooltip_text(
            _(
                "Free fly: WASD move. Click the view to look with the mouse; "
                "click again to release the cursor. "
                "Hold Shift: W/S go up/down. Turn off to restore the previous view."
            )
        )
        self.free_fly_button.connect("toggled", self._on_free_fly_toggled)
        self.nav_chrome.append(self.free_fly_button)

        self.add_overlay(self.nav_chrome)

    def clear_overlays(self) -> None:
        self.stats_overlay_label.set_visible(False)
        self.stats_overlay_label.set_label("")

    def sync_nav_cube(self) -> None:
        try:
            state = self.viewer.get_camera_state()
        except Exception:
            return
        self.nav_cube.sync_from_camera_state(state)

    def set_nav_cube_visible(self, visible: bool) -> None:
        self.nav_chrome.set_visible(bool(visible))

    def set_nav_cube_chrome_inset(self, margin_top: int, margin_end: int = 12) -> None:
        """Keep cube + Fly button clear of HeaderBar / window controls."""
        self.nav_chrome.set_margin_top(max(0, int(margin_top)))
        self.nav_chrome.set_margin_end(max(0, int(margin_end)))

    def is_free_fly(self) -> bool:
        return bool(self.free_fly_button.get_active())

    def _fly_view(self):
        getter = getattr(self.viewer, "get_view", None)
        if callable(getter):
            return getter()
        return None

    def _fly_world_up(self):
        key = "+Y"
        up_fn = getattr(self.viewer, "_engine_up_key", None)
        if callable(up_fn):
            try:
                key = up_fn()
            except Exception:
                key = "+Y"
        return UP_DIRS.get(key, (0.0, 1.0, 0.0))

    def _on_free_fly_toggled(self, button, *_args) -> None:
        if self._free_fly_block:
            return
        if button.get_active():
            self._enter_free_fly()
        else:
            self._exit_free_fly()

    def _enter_free_fly(self) -> None:
        """FPS fly: disable orbit gestures, WASD + mouse look, snapshot camera."""
        try:
            self._free_fly_camera_restore = self.viewer.get_camera_state()
        except Exception:
            self._free_fly_camera_restore = None

        view = self._fly_view()
        if view is None:
            return

        try:
            self._free_fly_interactive_restore = bool(
                view.get_property("interactive")
            )
        except Exception:
            self._free_fly_interactive_restore = True
        try:
            view.set_property("interactive", False)
        except Exception:
            pass

        try:
            view.set_focusable(True)
            view.grab_focus()
        except Exception:
            pass

        self._fly_keys.clear()
        self._fly_vel = (0.0, 0.0, 0.0)
        self._fly_look_vel = (0.0, 0.0)
        self._fly_pending_look = (0.0, 0.0)
        self._fly_last_frame_us = 0
        self._fly_cube_sync_skip = 0
        self._set_fly_look_active(False)
        self._install_fly_controllers(view)
        if not self._fly_tick_id:
            # Frame clock (not a 16ms timeout): one camera write per rendered
            # frame, so held keys can never outpace the renderer and stall input.
            self._fly_tick_id = self.add_tick_callback(self._fly_frame)
        self.sync_nav_cube()

    def _exit_free_fly(self) -> None:
        """Restore default orbit nav + camera from when Fly was enabled."""
        if self._fly_tick_id:
            try:
                self.remove_tick_callback(self._fly_tick_id)
            except Exception:
                pass
            self._fly_tick_id = 0
        self._fly_keys.clear()
        self._fly_vel = (0.0, 0.0, 0.0)
        self._fly_look_vel = (0.0, 0.0)
        self._fly_pending_look = (0.0, 0.0)
        self._set_fly_look_active(False)
        self._remove_fly_controllers()

        view = self._fly_view()
        if view is not None:
            try:
                view.set_property(
                    "interactive", bool(self._free_fly_interactive_restore)
                )
            except Exception:
                pass

        cam = self._free_fly_camera_restore
        self._free_fly_camera_restore = None
        if cam is not None:
            try:
                self.viewer.set_camera_state(cam)
            except Exception:
                reset = getattr(self.viewer, "reset_to_bounds", None)
                if callable(reset):
                    reset()
        else:
            reset = getattr(self.viewer, "reset_to_bounds", None)
            if callable(reset):
                reset()
        self.sync_nav_cube()

    def _set_fly_look_active(self, active: bool, *_xy) -> None:
        """Gate mouse-look: first view click engages, second releases cursor."""
        self._fly_look_active = bool(active)
        # Always re-seed from next overlay motion (view vs overlay coords differ).
        self._fly_last_xy = None
        self._fly_pending_look = (0.0, 0.0)
        if self._fly_look_active:
            try:
                self.nav_cube.set_can_target(False)
            except Exception:
                pass
        else:
            self._fly_look_vel = (0.0, 0.0)
            try:
                self.nav_cube.set_can_target(True)
            except Exception:
                pass

    def _fly_pointer_on_chrome(self, x: float, y: float) -> bool:
        """True when overlay coords hit cube / fly button (not the 3D view)."""
        try:
            ok, bounds = self.nav_chrome.compute_bounds(self)
        except Exception:
            return False
        if not ok:
            return False
        try:
            return bool(bounds.contains_point(float(x), float(y)))
        except Exception:
            return False

    def _install_fly_controllers(self, view) -> None:
        self._remove_fly_controllers()

        # Keys + motion on Overlay (CAPTURE) so WASD and look share one target.
        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._on_fly_key_pressed)
        key.connect("key-released", self._on_fly_key_released)
        self.add_controller(key)
        self._fly_key_ctrl = key
        try:
            self.set_focusable(True)
            self.grab_focus()
        except Exception:
            pass

        motion = Gtk.EventControllerMotion()
        motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        motion.connect("enter", self._on_fly_pointer_enter)
        motion.connect("leave", self._on_fly_pointer_leave)
        motion.connect("motion", self._on_fly_pointer_motion)
        self.add_controller(motion)
        self._fly_motion = motion

        # Click on the GL view toggles mouse-look (chrome keeps its own clicks).
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_fly_click_pressed)
        view.add_controller(click)
        self._fly_click = click

    def _on_fly_click_pressed(self, _gesture, _n_press, x, y) -> None:
        if not self.is_free_fly():
            return
        self._set_fly_look_active(not self._fly_look_active, x, y)
        try:
            self.grab_focus()
        except Exception:
            pass

    def _remove_fly_controllers(self) -> None:
        view = self._fly_view()
        for attr, widget in (
            ("_fly_key_ctrl", self),
            ("_fly_motion", self),
            ("_fly_click", view),
        ):
            ctrl = getattr(self, attr, None)
            setattr(self, attr, None)
            if ctrl is None or widget is None:
                continue
            try:
                widget.remove_controller(ctrl)
            except Exception:
                pass

    def _sync_fly_shift(self, state) -> None:
        if state & Gdk.ModifierType.SHIFT_MASK:
            self._fly_keys.add("shift")
        else:
            self._fly_keys.discard("shift")

    def _on_fly_key_pressed(self, _ctrl, keyval, _keycode, state) -> bool:
        if not self.is_free_fly():
            return False
        if keyval == Gdk.KEY_Escape and self._fly_look_active:
            self._set_fly_look_active(False)
            return True
        name = _FLY_KEYVALS.get(keyval)
        if name is None:
            self._sync_fly_shift(state)
            return False
        self._fly_keys.add(name)
        self._sync_fly_shift(state)
        return True

    def _on_fly_key_released(self, _ctrl, keyval, _keycode, state) -> bool:
        if not self.is_free_fly():
            return False
        name = _FLY_KEYVALS.get(keyval)
        if name is None:
            self._sync_fly_shift(state)
            return False
        self._fly_keys.discard(name)
        self._sync_fly_shift(state)
        return True

    def _on_fly_pointer_enter(self, _ctrl, x, y) -> None:
        if self._fly_look_active and not self._fly_pointer_on_chrome(x, y):
            self._fly_last_xy = (float(x), float(y))

    def _on_fly_pointer_leave(self, _ctrl) -> None:
        self._fly_last_xy = None

    def _on_fly_pointer_motion(self, _ctrl, x, y) -> None:
        """Queue look deltas only — tick applies look+move in one camera write."""
        if not self.is_free_fly() or not self._fly_look_active:
            return
        if self._fly_pointer_on_chrome(x, y):
            self._fly_last_xy = None
            return
        cur = (float(x), float(y))
        prev = self._fly_last_xy
        self._fly_last_xy = cur
        if prev is None:
            return
        dx = cur[0] - prev[0]
        dy = cur[1] - prev[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return
        self._fly_pending_look = (
            self._fly_pending_look[0] + dx,
            self._fly_pending_look[1] + dy,
        )
        self._fly_look_vel = (dx * FLY_LOOK_INERTIA, dy * FLY_LOOK_INERTIA)

    def _fly_wish_from_keys(self) -> tuple[float, float, float]:
        keys = self._fly_keys
        shift = "shift" in keys
        move_fwd = 0.0
        move_right = 0.0
        move_up = 0.0
        if shift:
            if "w" in keys:
                move_up += 1.0
            if "s" in keys:
                move_up -= 1.0
        else:
            if "w" in keys:
                move_fwd += 1.0
            if "s" in keys:
                move_fwd -= 1.0
        if "d" in keys:
            move_right += 1.0
        if "a" in keys:
            move_right -= 1.0
        return (move_fwd, move_right, move_up)

    def _fly_frame(self, _widget, frame_clock) -> bool:
        """Frame-clock driver: derive real dt, then run one fly step."""
        if not self.is_free_fly():
            self._fly_tick_id = 0
            return GLib.SOURCE_REMOVE
        now = 0
        try:
            now = int(frame_clock.get_frame_time())
        except Exception:
            now = 0
        prev = self._fly_last_frame_us
        self._fly_last_frame_us = now
        dt = FLY_DT
        if prev and now > prev:
            dt = min(0.05, max(1.0 / 240.0, (now - prev) / 1_000_000.0))
        self._fly_tick(dt)
        return GLib.SOURCE_CONTINUE

    def _fly_tick(self, dt: float = FLY_DT) -> bool:
        if not self.is_free_fly():
            return False

        # One camera write per frame: pending mouse look + coast + WASD move.
        # Separate motion set_camera_state was overwritten by move while keys held.
        look_dx = 0.0
        look_dy = 0.0
        if self._fly_look_active:
            # Look velocity is residual pixels per frame, so it is not dt-scaled.
            look_dx = self._fly_pending_look[0] + self._fly_look_vel[0]
            look_dy = self._fly_pending_look[1] + self._fly_look_vel[1]
            self._fly_pending_look = (0.0, 0.0)
            self._fly_look_vel = fly_look_velocity_step(self._fly_look_vel, dt=dt)
        else:
            self._fly_pending_look = (0.0, 0.0)
            self._fly_look_vel = (0.0, 0.0)

        wish = self._fly_wish_from_keys()
        self._fly_vel = fly_velocity_step(self._fly_vel, wish, dt=dt)
        vx, vy, vz = self._fly_vel
        moving = abs(vx) > 1e-9 or abs(vy) > 1e-9 or abs(vz) > 1e-9
        looking = abs(look_dx) > 1e-9 or abs(look_dy) > 1e-9
        if not moving and not looking:
            return False

        try:
            state = self.viewer.get_camera_state()
        except Exception:
            return False
        if state is None:
            return False

        world_up = self._fly_world_up()
        if looking:
            looked = fly_look(
                state,
                look_dx,
                look_dy,
                world_up=world_up,
                sens_deg=FLY_LOOK_SENS_DEG,
            )
            if looked is not None:
                state = looked

        if moving:
            unpacked = unpack_state(state)
            if unpacked is None:
                return False
            pos, focal, _up = unpacked
            dist = v_mod(v_sub(focal, pos))
            speed = fly_speed_for_distance(dist) * (dt / FLY_DT)
            moved = fly_move(
                state,
                move_fwd=vx,
                move_right=vy,
                move_up=vz,
                speed=speed,
                world_up=world_up,
            )
            if moved is not None:
                state = moved

        try:
            self.viewer.set_camera_state(state)
        except Exception:
            return False
        # Cube repaint is not worth a full redraw every frame while flying.
        self._fly_cube_sync_skip = (self._fly_cube_sync_skip + 1) % 6
        if self._fly_cube_sync_skip == 0:
            self.sync_nav_cube()
        return True

    def tab_title(self, modified_label: str = "modified", untitled: str = "Untitled") -> str:
        name = self.file_name or untitled
        if self.externally_modified:
            return f"{name} ({modified_label})"
        return name
