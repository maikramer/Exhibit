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
import json
import re
import threading
import logging

from gi.repository import Adw, Gtk, Gdk, Gio, GLib, GObject, Exb
from .file_row import FileRow
from wand.image import Image

from gettext import gettext as _

GObject.type_register(Exb.View)
GObject.type_register(Exb.Engine)

log = logging.getLogger(__name__)

up_dir_n_to_string = {
    0: "-X",
    1: "+X",
    2: "-Y",
    3: "+Y",
    4: "-Z",
    5: "+Z"
}

up_dir_string_to_n = {
    "-X": 0,
    "+X": 1,
    "-Y": 2,
    "+Y": 3,
    "-Z": 4,
    "+Z": 5
}

up_dirs_vector = {
    "-X": (-1.0, 0.0, 0.0),
    "+X": (1.0, 0.0, 0.0),
    "-Y": (0.0, -1.0, 0.0),
    "+Y": (0.0, 1.0, 0.0),
    "-Z": (0.0, 0.0, -1.0),
    "+Z": (0.0, 0.0, 1.0)
}

allowed_extensions = []

image_patterns = ["hdr", "exr", "png", "jpg", "pnm", "tiff", "bmp"]


class PeriodicChecker(GObject.Object):
    def __init__(self, function):
        super().__init__()

        self._running = False
        self._function = function

    def run(self):
        if self._running:
            return
        self._running = True
        GLib.timeout_add(500, self.periodic_check)

    def stop(self):
        self._running = False

    def periodic_check(self):
        if self._running:
            self._function()
            return True
        else:
            return False


settings = Gio.Settings.new('io.github.nokse22.Exhibit')


@Gtk.Template(resource_path='/io/github/nokse22/Exhibit/window.ui')
class ExbWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'ExbWindow'

    loading_label = Gtk.Template.Child()

    split_view = Gtk.Template.Child()

    viewer = Gtk.Template.Child()
    engine = Gtk.Template.Child()

    title_widget = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    toolbar_view = Gtk.Template.Child()

    view_drop_target = Gtk.Template.Child()
    loading_drop_target = Gtk.Template.Child()

    toast_overlay = Gtk.Template.Child()

    grid_switch = Gtk.Template.Child()
    absolute_grid_switch = Gtk.Template.Child()

    hdri_file_row = Gtk.Template.Child()
    up_direction_combo = Gtk.Template.Child()
    automatic_settings_switch = Gtk.Template.Child()
    automatic_reload_switch = Gtk.Template.Child()
    point_sprites_type_combo = Gtk.Template.Child()
    model_scivis_component_combo = Gtk.Template.Child()

    startup_stack = Gtk.Template.Child()

    settings_section = Gtk.Template.Child()

    animation_group = Gtk.Template.Child()
    play_button = Gtk.Template.Child()

    width = 600
    height = 600
    distance = 0

    file_name = ""
    filepath = ""
    no_file_loaded = True

    _cached_time_stamp = 0

    def __init__(self, application=None, startup_filepath=None):
        super().__init__(application=application)

        # Flags
        self.applying_breakpoint = False
        self.block_reload = True

        # Defining all the actions
        self.save_as_action = self.create_action(
            'save-as-image', self.open_save_file_chooser)
        self.open_new_action = self.create_action(
            'open-new', self.open_file_chooser)
        self.open_new_action = self.create_action(
            'add-new', self.open_file_chooser)

        self.orthographic_action = Gio.SimpleAction.new_stateful(
            "orthographic",
            None,
            GLib.Variant("b", False))
        self.add_action(self.orthographic_action)

        self.settings_action = Gio.SimpleAction.new_stateful(
            "settings",
            GLib.VariantType.new("s"),
            GLib.Variant("s", "general"))
        self.settings_action.connect(
            "change-state",
            lambda action, state: self.change_setting_state(state))
        self.add_action(self.settings_action)

        self.save_settings_action = self.create_action(
            'save-settings', self.on_save_settings)
        self.save_settings_action.set_enabled(False)

        # Saving all the useful paths
        data_home = os.environ["XDG_DATA_HOME"]

        self.hdri_path = data_home + "/HDRIs/"
        self.hdri_thumbnails_path = self.hdri_path + "/thumbnails/"

        self.user_configurations_path = data_home + "/configurations/"

        os.makedirs(self.user_configurations_path, exist_ok=True)
        os.makedirs(data_home + "/other files/", exist_ok=True)

        # Create the hdri folder and add the default if there are none
        self.setup_hdri_folder()

        # Setting drop target type
        self.view_drop_target.set_gtypes([Gdk.FileList])
        self.loading_drop_target.set_gtypes([Gdk.FileList])

        # Setting the window to the last state
        self.set_default_size(
            settings.get_int("startup-width"),
            settings.get_int("startup-height")
        )
        self.sidebar_default_visible = settings.get_boolean("startup-sidebar-show")
        self.split_view.set_show_sidebar(self.sidebar_default_visible)

        # Getting the saved HDRI and generating thumbnails
        self.hdri_file_row.file_patterns = image_patterns
        self.hdri_file_row.window = self

        for filename in list_files(self.hdri_path):
            name, _ = os.path.splitext(filename)

            thumbnail = self.hdri_thumbnails_path + name + ".jpeg"
            filepath = self.hdri_path + filename
            try:
                if not os.path.isfile(thumbnail):
                    thumbnail = self.generate_thumbnail(filepath)
                self.hdri_file_row.add_suggested_file(thumbnail, filepath)
            except Exception:
                log.warning(f"Couldn't open HDRI file {filepath}, skipping")

        self.style_manager = Adw.StyleManager().get_default()
        self.style_manager.connect(
            "notify::dark", self.update_background_color)

        self.update_background_color()

        self.play_button.connect("clicked", self.on_play_button_clicked)

        if startup_filepath:
            log.info(f"startup file detected: {startup_filepath}")
            self.load_file(filepath=startup_filepath)

        log.info("Started")

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
                log.info(f"Added {hdri_filename}")

    #
    # Functions that set the UI from the settings, triggered when
    #   a setting has changed.

    def set_up_direction_combo(self, *args):
        val = up_dir_string_to_n[self.engine.get_property("up").value]
        log.info(f"Setting up direction combo to {val}")
        self.up_direction_combo.set_selected(val)

    def set_scivis_component_combo(self, setting, *args):
        selected = self.model_scivis_component_combo.get_selected()
        log.debug(
            f"Setting scivis component combo, selected: {selected}")
        self.model_color_row.set_sensitive(True if selected == 0 else False)

        if (self.engine.get_property("scivis-component").value == -1 and
                self.engine.get_property("cells").value):
            self.model_scivis_component_combo.set_selected(0)
        else:
            self.model_scivis_component_combo.set_selected(
                -self.engine.get_property("scivis-component").value + 1)

    # Functions that are called when a UI changes, they should only
    #   set the corresponding setting.

    def on_up_direction_combo_changed(self, combo, *args):
        direction = up_dir_n_to_string[combo.get_selected()]
        self.engine.set_property("up", direction)

    def on_scivis_component_combo_changed(self, *args):
        selected = self.model_scivis_component_combo.get_selected()
        self.model_color_row.set_sensitive(True if selected == 0 else False)

        if selected == 0:
            self.engine.set_property("scivis-component", -1)
            self.engine.set_property("cells", True)
            self.engine.set_property("scivis-enabled", False)
        else:
            self.engine.set_property("scivis-component", -(selected - 1))
            self.engine.set_property("cells", False)
            self.engine.set_property("scivis-enabled", True)

    #
    #

    def update_background_color(self, *args):
        if self.style_manager.get_dark():
            self.engine.set_property("background-color", Gdk.RGBA(0.117, 0.117, 0.117, 1.0))
        else:
            self.engine.set_property("background-color", Gdk.RGBA(1.0, 1.0, 1.0, 1.0))

    def set_settings_from_name(self, name):
        log.debug("settings from name")
        if name == "custom":
            return

        # Get the default settings and change the ones defined by the chosen presets
        options = self.window_settings.get_default_user_customizable_settings()
        for key, value in self.configurations[name]["view-settings"].items():
            options[key] = value

        # Set all the settings
        for key, value in options.items():
            self.window_settings.set_setting(key, value)

        # Update all the viewer settings, to support settings without UI
        self.f3d_viewer.update_options(options)

        # Set all the settings not related to the viewer
        for key, value in self.configurations[name]["other-settings"].items():
            self.window_settings.set_setting(key, value)

    def check_for_options_change(self):
        if self.block_reload:
            return

        state_name = self.settings_action.get_state().get_string()
        if state_name == "custom":
            return

        log.debug(f"Checking for changed options from {state_name}")

        state_options = self.engine.get_default_user_customizable_settings()

        for key, value in self.configurations[state_name]["view-settings"].items():
            state_options[key] = value

        for key, value in self.configurations[state_name]["other-settings"].items():
            state_options[key] = value

        current_settings = self.engine.get_user_customized_settings()
        for key, value in state_options.items():
            if key in current_settings:
                if current_settings[key] != value:
                    log.info(
                        f"current key: {key}'s value is {current_settings[key]} != {value}")
                    self.change_setting_state(GLib.Variant("s", "custom"))
                    return

    # def periodic_check_for_file_change(self):
    #     if self.filepath == "":
    #         return True

    #     changed = self.update_time_stamp()
    #     if changed:
    #         log.debug("file changed")
    #         self.load_file(preserve_orientation=True, override=True)

    #     if settings.get_boolean("auto-reload"):
    #         return True
    #     return False

    def update_time_stamp(self):
        try:
            stamp = os.stat(self.filepath).st_mtime
            if stamp != self._cached_time_stamp:
                self._cached_time_stamp = stamp
                return True
            return False
        except Exception:
            return False

    def change_setting_state(self, state):
        log.debug(f"Requested changing settings to {state}")

        if state.get_string() == "custom":
            self.save_settings_action.set_enabled(True)
            self.settings_action.set_state(state)
            return

        self.set_propertys_from_name(state.get_string())

        self.settings_action.set_state(state)

        self.save_settings_action.set_enabled(False)

        self.update_background_color()

    def on_save_settings(self, *args):
        self.save_settings_name_entry.set_text("")
        self.save_settings_extensions_entry.set_text("")
        self.save_settings_expander.set_expanded(False)
        self.save_dialog.present(self)

    def open_file_chooser(self, *args):
        file_filter = Gtk.FileFilter(name=_("All supported formats"))

        allowed_extensions = Exb.get_allowed_extensions()

        for patt in allowed_extensions:
            file_filter.add_pattern("*." + patt)

        filter_list = Gio.ListStore.new(Gtk.FileFilter())
        filter_list.append(file_filter)

        dialog = Gtk.FileDialog(
            title=_("Open File"),
            filters=filter_list)

        dialog.open(self, None, self.on_open_file_response)

    def on_open_file_response(self, dialog, response):
        try:
            file = dialog.open_finish(response)
        except Exception as e:
            log.error(f"Exception Opening file: {e}")
            return

        if file:
            filepath = file.get_path()
            log.info("open file response")
            self.on_file_opened()
            self.viewer.get_engine().set_file(file)
            # self.load_file(filepath=filepath)

    def load_file(self, **kwargs):
        self.startup_stack.set_visible_child_name("loading_page")
        self.stack.set_visible_child_name("startup_page")
        self.loading_label.set_label(
            _("Loading {}").format(
                os.path.basename(kwargs.get("filepath", "Nothing"))))
        self.block_reload = True
        # self.viewer.initialize()
        # GLib.timeout_add(
        #     100,
        #     lambda *args: threading.Thread(
        #         target=self._load_file, kwargs=(kwargs)).start())

    def on_file_opened(self):
        log.debug("on file opened")

        self.update_time_stamp()
        # if settings.get_boolean("auto-reload"):
        #     self.change_checker.run()

        self.file_name = os.path.basename(self.filepath)

        self.set_title(_("Exhibit - {}").format(self.file_name))
        self.title_widget.set_subtitle(self.file_name)
        self.stack.set_visible_child_name("3d_page")
        self.viewer.grab_focus()

        self.no_file_loaded = False

        self.update_background_color()

        engine = self.viewer.get_engine()

        if engine.get_property("animations-n") == 0:
            self.animation_group.set_visible(False)
        else:
            self.animation_group.set_visible(True)

        self.block_reload = False

    def on_file_not_opened(self, filepath):
        log.debug("on file not opened")

        self.set_title(_("Exhibit"))
        if self.no_file_loaded:
            self.stack.set_visible_child_name("startup_page")
            self.startup_stack.set_visible_child_name("error_page")
        else:
            self.send_toast(_("Can't open") + " " + os.path.basename(filepath))

        self.update_background_color()

        self.block_reload = False

    def send_toast(self, message):
        toast = Adw.Toast(title=message, timeout=2)
        self.toast_overlay.add_toast(toast)

    def save_as_image(self, filepath):
        img = self.viewer.render_image()
        img.save(filepath)

    def open_save_file_chooser(self, *args):
        dialog = Gtk.FileDialog(
            title=_("Save File"),
            initial_name=self.file_name.split(".")[0] + ".png",
        )
        dialog.save(self, None, self.on_save_file_response)

    def on_save_file_response(self, dialog, response):
        try:
            file = dialog.save_finish(response)
        except Exception:
            return

        if file:
            file_path = file.get_path()
            self.save_as_image(file_path)
            toast = Adw.Toast(
                title="Image Saved",
                timeout=2,
                button_label="Open",
                action_name="app.show-image-externally",
                action_target=GLib.Variant("s", file_path)
            )
            self.toast_overlay.add_toast(toast)

    @Gtk.Template.Callback("on_home_clicked")
    def on_home_clicked(self, btn):
        self.engine.reset_camera()

    @Gtk.Template.Callback("on_open_button_clicked")
    def on_open_button_clicked(self, btn):
        self.open_file_chooser()

    def orthographic_state_changed(self, action, state):
        action.set_state(state)
        self.engine.set_property("orthographic", state.get_boolean())
        # self.viewer.update_options({"orthographic": state.get_boolean()})

    def on_orthographic_changed(self, setting, *args):
        self.orthographic_action.set_state(
            GLib.Variant(
                "b", self.engine.get_property("orthographic").value))

    def toggle_orthographic(self, *args):
        self.engine.set_property(
            "orthographic",
            not self.engine.get_property("orthographic").value)

    @Gtk.Template.Callback("on_drop_received")
    def on_drop_received(self, drop, value, x, y):
        file = value.get_files()[0]
        extension = os.path.splitext(file)[1][1:].lower()

        if extension in image_patterns:
            self.load_hdri(file)
        elif extension in allowed_extensions:
            log.info("drop received")
            self.load_file(file=file)

    @Gtk.Template.Callback("on_drop_enter")
    def on_drop_enter(self, drop_target, *args):
        drop_target.get_widget().set_visible_child_name("drop")

    @Gtk.Template.Callback("on_drop_leave")
    def on_drop_leave(self, drop_target, *args):
        drop_target.get_widget().set_visible_child_name("content")

    @Gtk.Template.Callback("on_close_sidebar_clicked")
    def on_close_sidebar_clicked(self, *args):
        self.split_view.set_show_sidebar(False)

    def open_with_external_app(self):
        try:
            file = Gio.File.new_for_path(self.filepath)
        except Exception:
            log.error("Failed to construct a new Gio.File from path.")
        else:
            launcher = Gtk.FileLauncher.new(file)
            launcher.set_always_ask(True)
            launcher.launch(self, None, None)

    @Gtk.Template.Callback("on_apply_breakpoint")
    def on_apply_breakpoint(self, *args):
        self.applying_breakpoint = True
        self.split_view.set_collapsed(True)
        self.split_view.set_show_sidebar(False)
        self.applying_breakpoint = False

    @Gtk.Template.Callback("on_unapply_breakpoint")
    def on_unapply_breakpoint(self, *args):
        self.applying_breakpoint = True
        self.split_view.set_collapsed(False)
        self.split_view.set_show_sidebar(self.sidebar_default_visible)
        self.applying_breakpoint = False

    @Gtk.Template.Callback("on_split_view_show_sidebar_changed")
    def on_split_view_show_sidebar_changed(self, *args):
        if self.applying_breakpoint:
            return
        self.sidebar_default_visible = self.split_view.get_show_sidebar()

    def on_play_button_clicked(self, btn):
        engine = self.viewer.get_engine()
        engine.play_animation()

    def on_playing_changed(self, *args):
        if self.viewer.playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
            self.play_button.set_tooltip_text(_("Stop"))
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")
            self.play_button.set_tooltip_text(_("Start"))

    #
    # Function called when the HDRI is deleted/added...

    def on_delete_skybox(self, *args):
        self.engine.set_property("hdri-file", None)
        self.engine.set_property("hdri-skybox", False)

    def load_hdri(self, filepath):
        self.engine.set_property("hdri-file", file)
        self.engine.set_property("hdri-skybox", True)

    def create_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        return action

    def generate_thumbnail(self, hdri_file_path, width=300, height=200):
        base_name = os.path.basename(hdri_file_path)
        name, _ = os.path.splitext(base_name)

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

    @Gtk.Template.Callback("on_close_request")
    def on_close_request(self, window):
        log.debug("window closed, saving settings")
        settings.set_int(
            "startup-width", window.get_width())
        settings.set_int(
            "startup-height", window.get_height())
        settings.set_boolean(
            "startup-sidebar-show", window.split_view.get_show_sidebar())
        settings.set_boolean(
            "auto-best", settings.get_boolean("auto-best"))


def list_files(directory):
    items = os.listdir(directory)
    files = [
        item for item in items if os.path.isfile(os.path.join(directory, item))
    ]
    return files

