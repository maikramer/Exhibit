# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings presets / HDRI setup helpers extracted from Viewer3dWindow."""

from __future__ import annotations

import json
import os

from gi.repository import Gio, GLib
from wand.image import Image

from .settings_compare import (
    formats_entry_to_pattern,
    preset_key_from_name,
    settings_values_equal,
)
from .file_patterns import allowed_extensions


class SettingsIOMixin:
    """Configuration presets and HDRI folder setup for ``Viewer3dWindow``."""

    def _settings_save_dialog(self):
        return getattr(self, "settings_dialog", None)

    def setup_configurations(self):
        self.configurations = Gio.resources_lookup_data(
            '/io/github/nokse22/Exhibit/configurations.json',
            Gio.ResourceLookupFlags.NONE).get_data().decode('utf-8')
        self.configurations = json.loads(self.configurations)

        required_keys = {
            "name", "formats",
            "view-settings", "other-settings"
        }

        for filename in os.listdir(self.user_configurations_path):
            if filename.endswith('.json'):
                filepath = os.path.join(
                    self.user_configurations_path, filename)
                with open(filepath, 'r') as file:
                    try:
                        configuration = json.load(file)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Error reading {filename}: {e}")
                        continue

                    if not isinstance(configuration, dict) or not configuration:
                        self.logger.error(
                            f"Error: {filepath} is not a non-empty object.")
                        continue

                    first_key_value = next(iter(configuration.values()))
                    if not isinstance(first_key_value, dict):
                        self.logger.error(
                            f"Error: {filepath} has invalid preset payload.")
                        continue

                    if required_keys.issubset(first_key_value.keys()):
                        self.configurations.update(configuration)
                    else:
                        self.logger.error(
                            f"Error: {filepath} is missing required keys.")

        item = Gio.MenuItem.new("Custom", "win.settings")
        item.set_attribute_value("target", GLib.Variant.new_string("custom"))
        self.settings_section.append_item(item)

        for key, setting in self.configurations.items():
            item = Gio.MenuItem.new(setting["name"], "win.settings")
            item.set_attribute_value("target", GLib.Variant.new_string(key))
            self.settings_section.append_item(item)

    def setup_hdri_folder(self):
        if os.path.isdir(self.hdri_path):
            return

        os.makedirs(self.hdri_path, exist_ok=True)
        os.makedirs(self.hdri_thumbnails_path, exist_ok=True)

        hdri_names = ["city.hdr", "meadow.hdr", "field.hdr", "sky.hdr"]
        for hdri_filename in hdri_names:
            if not os.path.isfile(self.hdri_path + hdri_filename):
                hdri = Gio.resources_lookup_data(
                    '/io/github/nokse22/Exhibit/HDRIs/' + hdri_filename,
                    Gio.ResourceLookupFlags.NONE).get_data()
                hdri_bytes = bytearray(hdri)
                with open(self.hdri_path + hdri_filename, 'wb') as output_file:
                    output_file.write(hdri_bytes)
                self.logger.info(f"Added {hdri_filename}")

    def on_save_settings_button_clicked(self, btn):
        dlg = self._settings_save_dialog()
        if dlg is None:
            return
        view_settings = self.window_settings.get_view_settings()
        other_settings = self.window_settings.get_other_settings()
        name = dlg.save_settings_name_entry.get_text()
        formats = dlg.save_settings_extensions_entry.get_text()

        # Format the key (reject ../ and other path junk)
        key = preset_key_from_name(name)
        filepath = os.path.join(self.user_configurations_path, f"{key}.json")
        configs_root = os.path.realpath(self.user_configurations_path)
        if os.path.commonpath(
                [os.path.realpath(filepath), configs_root]) != configs_root:
            self.logger.error("Refusing to write preset outside configs dir")
            return

        settings_dict = {
            key: {
                "name": name,
                "formats": formats_entry_to_pattern(formats),
                "view-settings": view_settings,
                "other-settings": other_settings
            }
        }

        with open(filepath, 'w') as j_f:
            json.dump(settings_dict, j_f, indent=4)

        self.configurations.update(settings_dict)
        item = Gio.MenuItem.new(name, "win.settings")
        item.set_attribute_value("target", GLib.Variant.new_string(key))
        self.settings_section.append_item(item)

        dlg.close()

    def on_save_settings_name_entry_changed(self, entry):
        dlg = self._settings_save_dialog()
        if dlg is None:
            return
        dlg.save_settings_button.set_sensitive(entry.get_text_length() != 0)

    def on_save_settings_extensions_entry_changed(self, entry):
        extensions_text = entry.get_text()

        if extensions_text == "":
            entry.remove_css_class("error")
            return

        entered_exts = [ext.strip() for ext in extensions_text.split(',')]

        if all(ext in allowed_extensions for ext in entered_exts):
            entry.remove_css_class("error")
        else:
            entry.add_css_class("error")

    def on_save_settings(self, *args):
        dlg = self._settings_save_dialog()
        if dlg is None:
            return
        bind = getattr(dlg, "bind_to_window", None)
        if callable(bind):
            bind(self)
        set_model = getattr(dlg, "set_settings_model", None)
        if callable(set_model):
            set_model(self.window_settings)
        dlg.save_settings_name_entry.set_text("")
        dlg.save_settings_extensions_entry.set_text("")
        dlg.save_settings_expander.set_expanded(False)
        dlg.save_settings_button.set_sensitive(False)
        dlg.present(self)

    def set_settings_from_name(self, name):
        self.logger.debug("settings from name")
        if name == "custom":
            return

        # Get the default settings and change the ones defined by the chosen presets
        options = self.window_settings.get_default_user_customizable_settings()
        for key, value in self.configurations[name]["view-settings"].items():
            options[key] = value

        prev_up = self.window_settings.get_setting("up").value
        prev_cb = self.window_settings.get_setting("checkerboard-enable").value

        # Batch view emits so presets do one update_options + one queue_render
        self.window_settings.begin_view_batch()
        for tab in self._iter_tabs():
            tab.viewer.begin_options_batch()
        try:
            for key, value in options.items():
                self.window_settings.set_setting(key, value)
            self._update_all_viewers_options(options, queue_render=False)
            for key, value in self.configurations[name]["other-settings"].items():
                self.window_settings.set_setting(key, value)
        finally:
            self.window_settings.end_view_batch()
            for tab in self._iter_tabs():
                tab.viewer.end_options_batch()

        # Batch suppresses changed-view → reload up/checkerboard explicitly.
        new_up = self.window_settings.get_setting("up").value
        new_cb = self.window_settings.get_setting("checkerboard-enable").value
        if new_up != prev_up or new_cb != prev_cb:
            preserve = new_up == prev_up
            for tab in self._iter_tabs():
                if not getattr(tab, "loaded", False) or not tab.filepath:
                    continue
                self._reload_tab(tab, preserve_orientation=preserve)
            if getattr(self, "_split_compare", False):
                GLib.idle_add(self._load_split_compare_from_active)

    def check_for_options_change(self):
        if self.block_reload:
            return

        state_name = self.settings_action.get_state().get_string()
        if state_name == "custom":
            return

        self.logger.debug(f"Checking for changed options from {state_name}")

        state_options = self.window_settings.get_default_user_customizable_settings()

        for key, value in self.configurations[state_name]["view-settings"].items():
            state_options[key] = value

        for key, value in self.configurations[state_name]["other-settings"].items():
            state_options[key] = value

        current_settings = self.window_settings.get_user_customized_settings()
        for key, value in state_options.items():
            if key in current_settings:
                if self._settings_values_equal(current_settings[key], value):
                    continue
                self.logger.info(
                    f"current key: {key}'s value is {current_settings[key]} != {value}")
                self.change_setting_state(GLib.Variant("s", "custom"))
                return

    @staticmethod
    def _settings_values_equal(a, b) -> bool:
        """Compare setting values; normalize RGB list/tuple mismatches from JSON."""
        return settings_values_equal(a, b)

    def on_delete_skybox(self, *args):
        self.window_settings.set_setting("hdri-file", "")
        self.window_settings.set_setting("hdri-skybox", False)
        switch = getattr(self, "use_skybox_switch", None)
        if switch is not None:
            switch.set_active(False)
        self._update_all_viewers_options(
            {"hdri-file": "", "hdri-skybox": False}
        )
        self.check_for_options_change()

    def generate_thumbnail(self, hdri_file_path, width=300, height=200):
        """Legacy helper; FileRow.generate_thumbnail is preferred for suggestions."""
        base_name = os.path.basename(hdri_file_path)
        name, _ext = os.path.splitext(base_name)

        thumbnail_name = f"{name}.jpeg"
        thumbnail_filepath = os.path.join(
            self.hdri_thumbnails_path, thumbnail_name)

        if os.path.isfile(thumbnail_filepath):
            return thumbnail_filepath
        try:
            with Image(filename=hdri_file_path) as img:
                img.thumbnail(width, height)
                img.gamma(1.7)
                img.brightness_contrast(0, -5)
                img.format = "jpeg"
                img.save(filename=thumbnail_filepath)
        except Exception as exc:
            self.logger.debug("generate_thumbnail: %s", exc)
            return None

        return thumbnail_filepath

