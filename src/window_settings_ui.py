# window_settings_ui.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Settings ↔ widget binding helpers extracted from Viewer3dWindow."""

from __future__ import annotations

from gi.repository import Gdk

up_dir_n_to_string = {
    0: "-X",
    1: "+X",
    2: "-Y",
    3: "+Y",
    4: "-Z",
    5: "+Z",
}

up_dir_string_to_n = {
    "-X": 0,
    "+X": 1,
    "-Y": 2,
    "+Y": 3,
    "-Z": 4,
    "+Z": 5,
}


def list_to_rgb(lst):
    return f"rgb({int(lst[0] * 255)},{int(lst[1] * 255)},{int(lst[2] * 255)})"


def rgb_to_list(rgb):
    values = tuple(int(x) / 255 for x in rgb[4:-1].split(","))
    return values


class SettingsUIMixin:
    _SPRITE_TYPES = ("sphere", "gaussian", "circle", "cross", "stddev", "bound")

    def set_hdri_file_row(self, setting, name, enum):
        self.logger.info(f"Setting hdri file row filename to {setting.value}")
        self.hdri_file_row.set_filename(setting.value)

    def set_switch_to(self, setting, name, enum, switch):
        self.logger.info(f"Setting switch to {setting.value}")
        switch.set_active(setting.value)

    def set_spin_to(self, setting, name, enum, spin):
        self.logger.info(f"Setting spin to {setting.value}")
        spin.set_value(setting.value)

    def set_up_direction_combo(self, *args):
        val = up_dir_string_to_n[self.window_settings.get_setting("up").value]
        self.logger.info(f"Setting up direction combo to {val}")
        self.up_direction_combo.set_selected(val)

    def set_color_button(self, setting, name, enum, color_button):
        rgba = Gdk.RGBA()
        rgba.parse(list_to_rgb(setting.value))
        color_button.set_rgba(rgba)

    def set_scivis_component_combo(self, setting, *args):
        selected = self.model_scivis_component_combo.get_selected()
        self.logger.debug(
            f"Setting scivis component combo, selected: {selected}")
        self.model_color_row.set_sensitive(True if selected == 0 else False)

        if (self.window_settings.get_setting("scivis-component").value == -1 and
                self.window_settings.get_setting("cells").value):
            self.model_scivis_component_combo.set_selected(0)
        else:
            self.model_scivis_component_combo.set_selected(
                -self.window_settings.get_setting("scivis-component").value + 1)

    def set_point_sprites_type_combo_changed(self, setting, *args):
        value = self.window_settings.get_setting("sprites-type").value
        try:
            index = self._SPRITE_TYPES.index(value)
        except ValueError:
            index = 0
        self.point_sprites_type_combo.set_selected(index)

    def on_switch_toggled(self, switch, active, name):
        self.window_settings.set_setting(name, switch.get_active())

    def on_spin_changed(self, spin, value, name):
        val = float(round(spin.get_value(), 2))
        self.window_settings.set_setting(name, val)

    def on_color_changed(self, btn, color, setting):
        color_list = rgb_to_list(btn.get_rgba().to_string())
        self.window_settings.set_setting(setting, color_list)

    def on_up_direction_combo_changed(self, combo, *args):
        direction = up_dir_n_to_string[combo.get_selected()]
        self.window_settings.set_setting("up", direction)

    def on_scivis_component_combo_changed(self, *args):
        selected = self.model_scivis_component_combo.get_selected()
        self.model_color_row.set_sensitive(True if selected == 0 else False)

        if selected == 0:
            self.window_settings.set_setting("scivis-component", -1, False)
            self.window_settings.set_setting("cells", True)
            self.window_settings.set_setting("scivis-enabled", False)
        else:
            self.window_settings.set_setting("scivis-component", -(selected - 1))
            self.window_settings.set_setting("cells", False)
            self.window_settings.set_setting("scivis-enabled", True)

    _SKIN_WEIGHT_MODES = (
        "magnitude",
        "slot0",
        "slot1",
        "slot2",
        "slot3",
        "bone",
    )

    def set_skin_weights_mode_combo(self, setting, *args):
        value = str(
            self.window_settings.get_setting("skin-weights-mode").value
            or "magnitude"
        )
        try:
            index = self._SKIN_WEIGHT_MODES.index(value)
        except ValueError:
            index = 0
        self.skin_weights_mode_combo.set_selected(index)
        self._refresh_skin_weights_joint_combo()

    def on_skin_weights_mode_combo_changed(self, *args):
        selected = self.skin_weights_mode_combo.get_selected()
        if selected < 0 or selected >= len(self._SKIN_WEIGHT_MODES):
            value = "magnitude"
        else:
            value = self._SKIN_WEIGHT_MODES[selected]
        self.window_settings.set_setting("skin-weights-mode", value, False)
        self._refresh_skin_weights_joint_combo()

    def on_skin_weights_joint_combo_changed(self, *args):
        selected = int(self.skin_weights_joint_combo.get_selected())
        if selected < 0:
            return
        self.window_settings.set_setting("skin-weights-joint", selected, False)

    def point_sprites_type_combo_changed(self, *args):
        selected = self.point_sprites_type_combo.get_selected()
        if selected < 0 or selected >= len(self._SPRITE_TYPES):
            value = "sphere"
        else:
            value = self._SPRITE_TYPES[selected]
        # update=False avoids combo re-entry; still emit changed-view → viewer.
        self.window_settings.set_setting("sprites-type", value, False)
