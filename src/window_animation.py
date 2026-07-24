# window_animation.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Animation combo / scrubber helpers extracted from Viewer3dWindow."""

from __future__ import annotations

from gettext import gettext as _
from gi.repository import GObject, Gtk


class AnimationMixin:
    def _unbind_animation_controls(self, viewer=None) -> None:
        """Drop scrubber bindings / playing handler (optionally for one viewer)."""
        log = getattr(self, "logger", None)
        for binding in self._anim_bindings:
            try:
                binding.unbind()
            except Exception as exc:
                if log:
                    log.debug("anim unbind failed: %s", exc)
        self._anim_bindings = []
        handler_id = self._playing_handler_id
        self._playing_handler_id = 0
        if not handler_id:
            return
        viewers = [viewer] if viewer is not None else [
            tab.viewer for tab in self._iter_tabs()
        ]
        for candidate in viewers:
            if candidate is None:
                continue
            try:
                if candidate.handler_is_connected(handler_id):
                    candidate.disconnect(handler_id)
                    return
            except Exception as exc:
                if log:
                    log.debug("anim disconnect playing handler failed: %s", exc)

    def _bind_animation_controls(self, viewer):
        self._unbind_animation_controls()
        flags_range = GObject.BindingFlags.BIDIRECTIONAL
        flags_value = (
            GObject.BindingFlags.BIDIRECTIONAL
            | GObject.BindingFlags.SYNC_CREATE)
        self._anim_bindings = [
            self.animation_time_adj.bind_property(
                "lower", viewer, "lower-time-range", flags_range),
            self.animation_time_adj.bind_property(
                "upper", viewer, "upper-time-range", flags_range),
            self.animation_time_adj.bind_property(
                "value", viewer, "animation-time", flags_value),
        ]
        self._playing_handler_id = viewer.connect(
            "notify::playing", self.on_playing_changed)
        self.on_playing_changed()

    def _animation_index_from_combo(self):
        selected = self.animation_combo.get_selected()
        if selected == Gtk.INVALID_LIST_POSITION or selected == 0:
            # First item is "None" → no clip / bind pose
            return None
        # Second item is "All animations" → -1
        if selected == 1:
            return -1
        return int(selected) - 2

    def _combo_position_for_animation_index(self, index):
        if index is None:
            return 0
        if index < 0:
            return 1
        return int(index) + 2

    def _set_animation_controls_sensitive(self, enabled: bool) -> None:
        self.play_button.set_sensitive(enabled)
        self.animation_time_scale.set_sensitive(enabled)

    def refresh_animation_combo(self):
        count = self.f3d_viewer.available_animations()
        if count <= 0:
            self.animation_group.set_visible(False)
            self.animation_time_scale.clear_marks()
            self._set_animation_controls_sensitive(False)
            return

        names = self.f3d_viewer.get_animation_names()
        string_list = Gtk.StringList()
        string_list.append(_("None"))
        string_list.append(_("All animations"))
        for i in range(count):
            name = names[i] if i < len(names) else ""
            if name:
                string_list.append(name)
            else:
                string_list.append(_("Animation {}").format(i))

        current = self.window_settings.get_setting("animation-index").value
        if isinstance(current, int) and current >= count:
            current = None
            self.window_settings.set_setting("animation-index", current, False)

        position = self._combo_position_for_animation_index(current)
        if position >= string_list.get_n_items():
            position = 0

        self._block_animation_combo = True
        try:
            self.animation_combo.set_model(string_list)
            self.animation_combo.set_selected(position)
        finally:
            self._block_animation_combo = False

        self.animation_group.set_visible(True)
        self._set_animation_controls_sensitive(current is not None)
        if current is None:
            self.animation_time_adj.set_lower(0)
            self.animation_time_adj.set_upper(0)
            self.animation_time_scale.clear_marks()
        else:
            lower = self.f3d_viewer.lower_time_range
            upper = self.f3d_viewer.upper_time_range
            self.animation_time_adj.set_lower(lower)
            self.animation_time_adj.set_upper(upper)
            self._refresh_animation_keyframe_marks()

    def on_animation_combo_changed(self, *args):
        if self._block_animation_combo:
            return

        index = self._animation_index_from_combo()
        self.window_settings.set_setting("animation-index", index)
        self.f3d_viewer.update_options({"animation-index": index})
        self.f3d_viewer.playing = False
        # Clip switches via scene.animation.indices. Returning to None needs a
        # reimport — clearing indices alone leaves the last skin pose.
        if index is None:
            if not self.f3d_viewer.reset_to_bind_pose():
                self.send_toast(_("Couldn't reset animation pose"))
            self._set_animation_controls_sensitive(False)
            self.animation_time_adj.set_lower(0)
            self.animation_time_adj.set_upper(0)
            self.f3d_viewer.notify("lower-time-range")
            self.f3d_viewer.notify("upper-time-range")
            self.animation_time_scale.clear_marks()
            return

        self._set_animation_controls_sensitive(True)
        lower = self.f3d_viewer.lower_time_range
        upper = self.f3d_viewer.upper_time_range
        self.animation_time_adj.set_lower(lower)
        self.animation_time_adj.set_upper(upper)
        self.f3d_viewer.notify("lower-time-range")
        self.f3d_viewer.notify("upper-time-range")
        self.f3d_viewer.animation_time = lower
        self._refresh_animation_keyframe_marks()

    def _refresh_animation_keyframe_marks(self) -> None:
        """Mark keyframe times on the scrubber (F3D get_animation_keyframes)."""
        scale = self.animation_time_scale
        scale.clear_marks()
        if not self.animation_group.get_visible():
            return
        keyframes = self.f3d_viewer.get_animation_keyframes()
        if not keyframes:
            return
        lower = self.animation_time_adj.get_lower()
        upper = self.animation_time_adj.get_upper()
        for time_value in keyframes:
            if time_value < lower or time_value > upper:
                continue
            scale.add_mark(time_value, Gtk.PositionType.TOP, None)
