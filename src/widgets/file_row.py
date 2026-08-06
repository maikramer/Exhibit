# window.py
#
# Copyright 2024-2025 Nokse <nokse@posteo.com>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from gi.repository import Adw, Gtk, Gdk, Gio, GObject
from wand.image import Image

from gettext import gettext as _

from ..config import *


class ImageThumbnail(Gtk.FlowBoxChild):
    __gtype_name__ = "ImageThumbnail"

    def __init__(self, file_thumbnail, hdri_file):
        super().__init__()

        self.hdri_file: Gio.File = Gio.File.new_for_path(hdri_file)

        file = Gio.File.new_for_path(file_thumbnail)
        image = Gtk.Picture(
            file=file,
            css_classes=["suggested-picture"],
            hexpand=True,
            vexpand=True,
            content_fit=Gtk.ContentFit.COVER,
        )
        self.set_child(image)

        base_name = os.path.basename(hdri_file)
        self.set_tooltip_text(base_name)


@Gtk.Template(resource_path="/io/github/nokse22/Exhibit/widgets/file_row.ui")
class FileRow(Adw.PreferencesRow):
    __gtype_name__ = "FileRow"

    file_button = Gtk.Template.Child()
    filename_label = Gtk.Template.Child()
    delete_button = Gtk.Template.Child()
    drop_target = Gtk.Template.Child()
    suggestions_box = Gtk.Template.Child()

    filepath = ""

    def __init__(self):
        super().__init__()

        self._file: Gio.File = None

        self.title = ""

        self.suggested_files_n = 0

        self.file_patterns = []
        self.window = None

        self.file_button.connect("clicked", self.on_open_clicked)
        self.delete_button.connect("clicked", self.on_delete_clicked)
        self.suggestions_box.connect("child-activated", self.on_image_activated)
        self.drop_target.connect("drop", self.on_drop_received)

        self.drop_target.set_gtypes([Gdk.FileList])

    @GObject.Property(type=Gio.File, default=None, flags=GObject.ParamFlags.READWRITE)
    def file(self):
        return self._file

    @file.setter
    def file(self, value):
        def _path(f):
            if f is None:
                return None
            try:
                return f.get_path()
            except Exception:
                return None

        new_path = _path(value)
        old_path = _path(self._file)
        if new_path == old_path and (value is None) == (self._file is None):
            # Same on-disk path — refresh label only, skip notify storms.
            filename = new_path
        else:
            self._file = value
            filename = new_path
            self.notify("file")

        if filename:
            self.filename_label.set_label(filename)
            self.filename_label.set_visible(True)
            self.filename_label.set_tooltip_text(filename)
            self.delete_button.set_visible(True)
        else:
            self.filename_label.set_visible(False)
            self.filename_label.set_tooltip_text("")
            self.delete_button.set_visible(False)

    def set_filename(self, filepath) -> None:
        """Settings / load_hdri API: path string → Gio.File property."""
        if not filepath:
            self.file = None
            return
        self.file = Gio.File.new_for_path(str(filepath))

    def _ensure_skybox_enabled(self) -> None:
        """Match window.load_hdri: picking an HDRI must show the skybox."""
        window = self.window
        if window is None:
            return
        try:
            settings = getattr(window, "window_settings", None)
            if settings is not None:
                settings.set_setting("hdri-skybox", True)
            switch = getattr(window, "use_skybox_switch", None)
            if switch is not None and not switch.get_active():
                switch.set_active(True)
            update = getattr(window, "_update_all_viewers_options", None)
            if callable(update):
                update({"hdri-skybox": True})
            check = getattr(window, "check_for_options_change", None)
            if callable(check):
                check()
        except Exception:
            pass

    def on_open_clicked(self, btn):
        self.on_open_file_dialog()

    def on_delete_clicked(self, *args):
        self.file = None
        # Pick enables skybox (r46); clear must disable it too or default HDRI shows.
        window = self.window
        if window is None:
            return
        clear = getattr(window, "on_delete_skybox", None)
        if callable(clear):
            try:
                clear()
            except Exception:
                pass
            return
        self._ensure_skybox_disabled()

    def _ensure_skybox_disabled(self) -> None:
        """Fallback when window.on_delete_skybox is unavailable."""
        window = self.window
        if window is None:
            return
        try:
            settings = getattr(window, "window_settings", None)
            if settings is not None:
                settings.set_setting("hdri-skybox", False)
            switch = getattr(window, "use_skybox_switch", None)
            if switch is not None and switch.get_active():
                switch.set_active(False)
            update = getattr(window, "_update_all_viewers_options", None)
            if callable(update):
                update({"hdri-skybox": False, "hdri-file": ""})
            check = getattr(window, "check_for_options_change", None)
            if callable(check):
                check()
        except Exception:
            pass

    def on_drop_received(self, drop, value, x, y):
        try:
            files = value.get_files()
        except Exception:
            return
        if not files:
            return
        file = files[0]
        filepath = file.get_path() if file is not None else None
        if not filepath:
            return
        extension = os.path.splitext(filepath)[1][1:].lower()
        if extension in self.file_patterns:
            self.file = file
            self._ensure_skybox_enabled()

    def add_suggested_file(self, filepath):
        if not os.path.isfile(filepath):
            return
        try:
            file_thumbnail = self.generate_thumbnail(filepath)
        except Exception:
            # Corrupt/unsupported HDRI must not abort suggestion population.
            return
        if not file_thumbnail:
            return
        self.suggestions_box.set_visible(True)
        hdri_thumbnail = ImageThumbnail(file_thumbnail, filepath)
        self.suggestions_box.append(hdri_thumbnail)
        self.suggested_files_n += 1
        height = ((self.suggested_files_n + 3) // 4) * 70
        self.suggestions_box.set_size_request(-1, height)

    def on_image_activated(self, flow_box, child):
        self.file = child.hdri_file
        self._ensure_skybox_enabled()

    def on_open_file_dialog(self, *args):
        file_filter = Gtk.FileFilter(name=_("All supported formats"))

        for patt in self.file_patterns:
            file_filter.add_pattern("*." + patt)

        filter_list = Gio.ListStore.new(Gtk.FileFilter())
        filter_list.append(file_filter)

        dialog = Gtk.FileDialog(
            title=_("Open File"),
            filters=filter_list,
        )

        dialog.open(self.window, None, self.on_open_file_dialog_file_response)

    def on_open_file_dialog_file_response(self, dialog, response):
        try:
            file = dialog.open_finish(response)
        except Exception:
            # Cancel / dismiss must not raise into the GTK dialog callback.
            return

        if file:
            self.file = file
            self._ensure_skybox_enabled()

    def generate_thumbnail(self, hdri_file_path, width=300, height=200):
        base_name = os.path.basename(hdri_file_path)
        name, _ = os.path.splitext(base_name)

        thumbnail_name = f"{name}.jpeg"
        thumbnail_filepath = os.path.join(HDRI_TN_PATH, thumbnail_name)

        if os.path.isfile(thumbnail_filepath):
            return thumbnail_filepath

        try:
            with Image(filename=hdri_file_path) as img:
                img.thumbnail(width, height)
                img.gamma(1.7)
                img.brightness_contrast(0, -5)
                img.format = "jpeg"
                img.save(filename=thumbnail_filepath)
        except Exception:
            return None

        return thumbnail_filepath
