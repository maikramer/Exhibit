# settings_dialog.py
#
# Copyright 2026 Nokse <nokse@posteo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Gtk, Adw


@Gtk.Template(resource_path='/io/github/nokse22/Exhibit/settings_dialog.ui')
class ExhibitSettingsDialog(Adw.Dialog):
    __gtype_name__ = "ExhibitSettingsDialog"

    settings_column_view = Gtk.Template.Child()
    settings_column_view_name_column = Gtk.Template.Child()
    settings_column_view_value_column = Gtk.Template.Child()
    save_settings_button = Gtk.Template.Child()
    save_settings_name_entry = Gtk.Template.Child()
    save_settings_extensions_entry = Gtk.Template.Child()
    save_settings_expander = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Setting up the save settings dialog
        def _on_factory_setup(_factory, list_item):
            label = Gtk.Label(xalign=0, ellipsize=3)
            list_item.set_child(label)

        def _on_factory_bind(_factory, list_item, what):
            label_widget = list_item.get_child()
            setting = list_item.get_item()
            label_widget.set_label(str(getattr(setting, what)))

        self.settings_column_view_name_column.get_factory().connect(
            "setup", _on_factory_setup)
        self.settings_column_view_name_column.get_factory().connect(
            "bind", _on_factory_bind, "name")
        self.settings_column_view_value_column.get_factory().connect(
            "setup", _on_factory_setup)
        self.settings_column_view_value_column.get_factory().connect(
            "bind", _on_factory_bind, "value")

        selection = Gtk.NoSelection.new()
        self.settings_column_view.set_model(model=selection)

        self.save_settings_button.connect(
            "clicked", self.on_save_settings_button_clicked)
        self.save_settings_name_entry.connect(
            "changed", self.on_save_settings_name_entry_changed)
        self.save_settings_extensions_entry.connect(
            "changed", self.on_save_settings_extensions_entry_changed)

    def on_save_settings_button_clicked(self, btn):
        # Extract view settings, name, and formats
        view_settings = self.engine.get_view_settings()
        other_settings = self.engine.get_other_settings()
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
        # else:
