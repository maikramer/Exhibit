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


@Gtk.Template(resource_path='/io/github/nokse22/Exhibit/widgets/settings_dialog.ui')
class SettingsDialog(Adw.Dialog):
    __gtype_name__ = "SettingsDialog"

    settings_column_view = Gtk.Template.Child()
    settings_column_view_name_column = Gtk.Template.Child()
    settings_column_view_value_column = Gtk.Template.Child()
    save_settings_button = Gtk.Template.Child()
    save_settings_name_entry = Gtk.Template.Child()
    save_settings_extensions_entry = Gtk.Template.Child()
    save_settings_expander = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._owner = None
        self._wired = False

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

        self.settings_column_view.set_model(Gtk.NoSelection.new())

    def bind_to_window(self, window) -> None:
        """Wire save controls to ``SettingsIOMixin`` on the owning window."""
        self._owner = window
        if self._wired or window is None:
            return
        self.save_settings_button.connect(
            "clicked", window.on_save_settings_button_clicked)
        self.save_settings_name_entry.connect(
            "changed", window.on_save_settings_name_entry_changed)
        self.save_settings_extensions_entry.connect(
            "changed", window.on_save_settings_extensions_entry_changed)
        self._wired = True

    def set_settings_model(self, model) -> None:
        self.settings_column_view.set_model(Gtk.NoSelection.new(model))
