# window_animation.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Animation combo / scrubber helpers extracted from Viewer3dWindow."""

from __future__ import annotations

from gettext import gettext as _
from gi.repository import Gtk


class AnimationMixin:
    def _unbind_animation_controls(self, viewer=None) -> None:
        """Drop playing handler (optionally for one viewer)."""
        log = getattr(self, "logger", None)
        # Legacy property binds (removed); keep list clear for safety.
        for binding in getattr(self, "_anim_bindings", []) or []:
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

    def _sync_animation_scrubber(self, viewer) -> None:
        """Point the visible scrubber at the active tab engine adjustment (ms)."""
        if viewer is None:
            return
        scale = getattr(self, "animation_time_scale", None)
        engine = getattr(viewer, "engine", None)
        if scale is None or engine is None:
            return
        try:
            adj = engine.get_property("animation-adjustment")
        except Exception as exc:
            log = getattr(self, "logger", None)
            if log:
                log.debug("animation-adjustment: %s", exc)
            return
        if adj is None:
            return
        scale.set_adjustment(adj)
        self.animation_time_adj = adj
        # Keep Python range props in seconds for any remaining callers.
        try:
            viewer.lower_time_range = float(adj.get_lower()) / 1000.0
            viewer.upper_time_range = float(adj.get_upper()) / 1000.0
        except Exception:
            pass

    def _bind_animation_controls(self, viewer):
        self._unbind_animation_controls()
        self._sync_animation_scrubber(viewer)
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
        play_header = getattr(self, "play_button_headerbar", None)
        if play_header is not None:
            play_header.set_sensitive(enabled)
        scale = getattr(self, "animation_time_scale", None)
        if scale is not None:
            scale.set_sensitive(enabled)

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
        self._sync_animation_scrubber(self.f3d_viewer)
        if current is None:
            self.animation_time_scale.clear_marks()
        else:
            self._refresh_animation_keyframe_marks()

    def on_animation_combo_changed(self, *args):
        if self._block_animation_combo:
            return

        index = self._animation_index_from_combo()
        # Batch so changed-view does not push animation-index onto sibling tabs.
        self.window_settings.begin_view_batch()
        try:
            self.window_settings.set_setting("animation-index", index)
        finally:
            self.window_settings.end_view_batch()
        self.f3d_viewer.update_options({"animation-index": index})
        self.f3d_viewer.playing = False
        # Clip switches via scene.animation.indices. Returning to None needs a
        # reimport — clearing indices alone leaves the last skin pose.
        if index is None:
            if not self.f3d_viewer.reset_to_bind_pose():
                self.send_toast(_("Couldn't reset animation pose"))
            self._set_animation_controls_sensitive(False)
            self._sync_animation_scrubber(self.f3d_viewer)
            self.animation_time_scale.clear_marks()
            return

        self._set_animation_controls_sensitive(True)
        self._sync_animation_scrubber(self.f3d_viewer)
        self._refresh_animation_keyframe_marks()

    def _refresh_animation_keyframe_marks(self) -> None:
        """Mark keyframe times on the scrubber (ms units, matching engine adj)."""
        scale = self.animation_time_scale
        scale.clear_marks()
        if not self.animation_group.get_visible():
            return
        keyframes = self.f3d_viewer.get_animation_keyframes()
        if not keyframes:
            return
        adj = self.animation_time_adj
        lower = adj.get_lower()
        upper = adj.get_upper()
        for time_value in keyframes:
            # Viewer may report seconds; engine adj is ms.
            mark = float(time_value)
            if mark <= upper / 50.0:  # likely seconds if tiny vs ms upper
                mark *= 1000.0
            if mark < lower or mark > upper:
                continue
            scale.add_mark(mark, Gtk.PositionType.TOP, None)
