# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings presets / HDRI setup helpers extracted from Viewer3dWindow."""

from __future__ import annotations

import json
import os

from gi.repository import Gio, GLib
from wand.image import Image

from .settings_compare import settings_values_equal
from .file_patterns import allowed_extensions


class SettingsIOMixin:
    """Configuration presets and HDRI folder setup for ``Viewer3dWindow``."""

    def setup_configurations(self):
        self.configurations = Gio.resources_lookup_data(
            '/io/github/nokse22/Exhibit/configurations.json',
            Gio.ResourceLookupFlags.NONE).get_data().decode('utf-8')
        self.configurations = json.loads(self.configurations)

        for filename in os.listdir(self.user_configurations_path):
            if filename.endswith('.json'):
                filepath = os.path.join(
                    self.user_configurations_path, filename)
                with open(filepath, 'r') as file:
                    try:
                        configuration = json.load(file)

                        # Check if the loaded configurations
                        #   has all the required keys
                        required_keys = {
                            "name", "formats",
                            "view-settings", "other-settings"
                        }
                        first_key_value = next(iter(configuration.values()))
                        if required_keys.issubset(first_key_value.keys()):
                            self.configurations.update(configuration)
                        else:
                            self.logger.error(
                                f"Error: {filepath} is missing required keys.")

                    except json.JSONDecodeError as e:
                        self.logger.error(f"Error reading {filename}: {e}")

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
        # Extract view settings, name, and formats
        view_settings = self.window_settings.get_view_settings()
        other_settings = self.window_settings.get_other_settings()
        name = self.save_settings_name_entry.get_text()
        formats = self.save_settings_extensions_entry.get_text()

        # Format the key
        key = name.lower().replace(' ', '_')

        # Construct the dictionary
        settings_dict = {
            key: {
                "name": name,
                "formats": f".*({formats.replace(', ', '|')})",
                "view-settings": view_settings,
                "other-settings": other_settings
            }
        }

        # Save to JSON file
        with open(self.user_configurations_path + key + '.json', 'w') as j_f:
            json.dump(settings_dict, j_f, indent=4)

        # Update configurations and menu UI
        self.configurations.update(settings_dict)
        item = Gio.MenuItem.new(name, "win.settings")
        item.set_attribute_value("target", GLib.Variant.new_string(key))
        self.settings_section.append_item(item)

        self.save_dialog.close()

    def on_save_settings_name_entry_changed(self, entry):
        if entry.get_text_length() != 0:
            self.save_settings_button.set_sensitive(True)
        else:
            self.save_settings_button.set_sensitive(False)

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
        self.save_settings_name_entry.set_text("")
        self.save_settings_extensions_entry.set_text("")
        self.save_settings_expander.set_expanded(False)
        self.save_dialog.present(self)

    def set_settings_from_name(self, name):
        self.logger.debug("settings from name")
        if name == "custom":
            return

        # Get the default settings and change the ones defined by the chosen presets
        options = self.window_settings.get_default_user_customizable_settings()
        for key, value in self.configurations[name]["view-settings"].items():
            options[key] = value

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
        self.use_skybox_switch.set_active(False)
        options = {
            "hdri-file": "",
            "hdri-skybox": False}
        self._update_all_viewers_options(options)
        self.check_for_options_change()

    def generate_thumbnail(self, hdri_file_path, width=300, height=200):
        base_name = os.path.basename(hdri_file_path)
        name, _ext = os.path.splitext(base_name)

        thumbnail_name = f"{name}.jpeg"
        thumbnail_filepath = os.path.join(
            self.hdri_thumbnails_path, thumbnail_name)

        with Image(filename=hdri_file_path) as img:
            img.thumbnail(width, height)
            img.gamma(1.7)
            img.brightness_contrast(0, -5)
            img.format = 'jpeg'
            img.save(filename=thumbnail_filepath)

        return thumbnail_filepath

