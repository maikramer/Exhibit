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
import asyncio

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Exb

from wand.image import Image
from pathlib import Path

from .widgets.file_row import FileRow
from .widgets.settings_dialog import SettingsDialog
from .config import *
from .widgets.theme_switcher import ThemeSwitcher
from .meshopt_decompress import prepare_glb_for_load, release_prepared

from gettext import gettext as _

GObject.type_register(Exb.View)
GObject.type_register(Exb.Engine)
GObject.type_register(Exb.Blending)
GObject.type_register(Exb.Sprites)
GObject.type_register(Exb.AntiAliasing)
GObject.type_register(Exb.Direction)
GObject.type_register(SettingsDialog)

log = logging.getLogger(__name__)

image_patt = ["hdr", "exr", "png", "jpg", "pnm", "tiff", "bmp"]
model_patt = [s for s in Exb.get_allowed_extensions() if s not in image_patt]

settings = Gio.Settings.new('io.github.nokse22.Exhibit')


@Gtk.Template(resource_path='/io/github/nokse22/Exhibit/window.ui')
class ExbWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'ExbWindow'

    settings_dialog = Gtk.Template.Child()

    split_view = Gtk.Template.Child()

    viewer = Gtk.Template.Child()
    engine = Gtk.Template.Child()

    title_widget = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    toolbar_view = Gtk.Template.Child()

    view_drop_target = Gtk.Template.Child()
    loading_drop_target = Gtk.Template.Child()

    toast_overlay = Gtk.Template.Child()

    hdri_file_row = Gtk.Template.Child()
    up_direction_combo = Gtk.Template.Child()
    model_scivis_component_combo = Gtk.Template.Child()

    startup_stack = Gtk.Template.Child()
    settings_section = Gtk.Template.Child()

    animation_combo_model = Gtk.Template.Child()
    animation_group = Gtk.Template.Child()
    play_button = Gtk.Template.Child()

    loading_status_page = Gtk.Template.Child()

    primary_menu_button = Gtk.Template.Child()

    width = 600
    height = 600
    distance = 0

    file_name = ""
    filepath = ""
    no_file_loaded = True

    _cached_time_stamp = 0

    # Compatibility aliases while fork mixins are re-wired onto Exb.
    @property
    def f3d_viewer(self):
        return self.viewer


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
        # self.save_settings_action.set_enabled(False)

        theme_action = Gio.SimpleAction.new_stateful(
            "theme",
            GLib.VariantType.new("s"),
            GLib.Variant("s", settings.get_string("theme")),
        )
        theme_action.connect("activate", self.set_theme_action)
        self.add_action(theme_action)

        popover = self.primary_menu_button.get_popover()
        theme_switcher = ThemeSwitcher()
        popover.add_child(theme_switcher, "theme")

        # Creating folders if needed
        Path(PRESETS_PATH).mkdir(parents=True, exist_ok=True)
        Path(HDRI_PATH).mkdir(parents=True, exist_ok=True)
        Path(HDRI_TN_PATH).mkdir(parents=True, exist_ok=True)

        self.presets = Exb.Presets.new_with_paths([PRESETS_PATH])

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
        self.hdri_file_row.file_patterns = image_patt
        self.hdri_file_row.window = self

        for filename in Path(HDRI_PATH).iterdir():
            try:
                filepath = Path(HDRI_PATH) / filename
                self.hdri_file_row.add_suggested_file(filepath)
            except Exception as e:
                log.warning(f"Couldn't open HDRI file {filepath}: {e}")

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
        hdri_names = ["city.hdr", "meadow.hdr", "field.hdr", "sky.hdr"]
        for hdri_filename in hdri_names:
            if not os.path.isfile(HDRI_PATH + hdri_filename):
                hdri = Gio.resources_lookup_data(
                    RESOURCES_PREFIX + "HDRIs/" + hdri_filename,
                    Gio.ResourceLookupFlags.NONE).get_data()
                hdri_bytes = bytearray(hdri)
                with open(Path(HDRI_PATH) / hdri_filename, 'wb') as output_file:
                    output_file.write(hdri_bytes)
                log.info(f"Added {hdri_filename}")

    def set_theme_action(self, action, variant):
        manager = Adw.StyleManager().get_default()
        value = variant.get_string()
        match value:
            case "default":
                manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
            case "light":
                manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            case "dark":
                manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        settings.set_string("theme", value)

    #
    #

    def update_background_color(self, *args):
        if self.style_manager.get_dark():
            self.engine.set_property("background-color", Gdk.RGBA(0.117, 0.117, 0.117, 1.0))
        else:
            self.engine.set_property("background-color", Gdk.RGBA(1.0, 1.0, 1.0, 1.0))

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
        self.settings_dialog.present(self)

    def open_file_chooser(self, *args):
        file_filter = Gtk.FileFilter(name=_("All supported formats"))

        for patt in model_patt:
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

        self.load_file(file)

    def load_file(self, file):
        if not file:
            return

        filepath = file.get_path()
        self.filepath = filepath or ""
        load_path = filepath

        # Fork prepare pipeline: meshopt / quantization / KTX2 before engine load.
        if filepath:
            try:
                load_path, _legacy_temp = prepare_glb_for_load(filepath)
            except Exception as e:
                log.warning("GLB prepare failed for %s: %s", filepath, e)
                load_path = filepath

        load_gio = (
            Gio.File.new_for_path(load_path)
            if load_path and load_path != filepath
            else file
        )

        self.engine.reset()
        preset = self.presets.get_default_for(filepath)
        self.engine.apply_preset(preset)

        self.loading_status_page.set_description(
            _("Loading {}").format(os.path.basename(filepath)))

        try:
            self.engine.load_file(load_gio)
        except Exception as e:
            log.warning("%s", e)
            if load_path and load_path != filepath:
                release_prepared(load_path)
            self.on_file_not_opened(filepath)
            return

        # Retain prepared path until next successful load / window close.
        prev = getattr(self, "_prepared_load_path", None)
        if prev and prev != load_path:
            release_prepared(prev)
        self._prepared_load_path = load_path if load_path != filepath else None

        self.on_file_opened()

    def on_file_opened(self):
        log.debug("on file opened")

        self.file_name = os.path.basename(self.filepath)

        self.set_title(_("Exhibit - {}").format(self.file_name))
        self.title_widget.set_subtitle(self.file_name)
        self.stack.set_visible_child_name("3d_page")
        self.viewer.grab_focus()

        self.no_file_loaded = False

        self.update_background_color()
        self.update_animation_ui()

    def on_file_not_opened(self, filepath):
        log.debug("on file not opened")

        self.set_title(_("Exhibit"))
        if self.no_file_loaded:
            self.stack.set_visible_child_name("startup_page")
            self.startup_stack.set_visible_child_name("error_page")
        else:
            self.send_toast(_("Can't open") + " " + os.path.basename(filepath))

        self.update_background_color()

    def update_animation_ui(self):
        # Clear existing rows (iterate backwards — Gio.ListModel).
        while self.animation_combo_model.get_n_items() > 0:
            self.animation_combo_model.remove(0)

        n = self.engine.get_animations_n()
        if n == 0:
            self.animation_group.set_visible(False)
            return

        self.animation_group.set_visible(True)
        names = self._animation_names_from_file(self.filepath, n)
        for name in names:
            self.animation_combo_model.append(name)

    def _animation_names_from_file(self, filepath, count):
        """Prefer glTF animation names; fall back to numbered clips."""
        names = []
        try:
            if filepath and str(filepath).lower().endswith((".glb", ".gltf")):
                from .gltf_scene_graph import _load_gltf

                gltf = _load_gltf(filepath) or {}
                anims = gltf.get("animations") or []
                for i, anim in enumerate(anims[:count]):
                    if isinstance(anim, dict):
                        names.append(anim.get("name") or str(i))
                    else:
                        names.append(str(i))
        except Exception as exc:
            log.debug("animation names: %s", exc)
        while len(names) < count:
            names.append(str(len(names)))
        return names

    def send_toast(self, message):
        toast = Adw.Toast(title=message, timeout=2)
        self.toast_overlay.add_toast(toast)

    def save_as_image(self, filepath):
        texture = self.engine.render_texture()
        if texture is None:
            self.send_toast(_("Couldn't save image"))
            return
        texture.save_to_filename(filepath)

    def open_save_file_chooser(self, *args):
        dialog = Gtk.FileDialog(
            title=_("Save File"),
            initial_name=self.file_name.split(".")[0] + ".png",
        )
        # Seed dialog from model folder when possible (fork UX).
        if self.filepath:
            try:
                parent = Gio.File.new_for_path(self.filepath).get_parent()
                if parent is not None:
                    dialog.set_initial_folder(parent)
            except Exception as exc:
                log.debug("save dialog folder: %s", exc)
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

        if extension in image_patt:
            self.load_hdri(file)
        elif extension in model_patt:
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
        file = self.engine.get_file()
        if file:
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
        self.engine.play_animation()
        self.on_playing_changed()

    def on_playing_changed(self, *args):
        # Exb.View has no playing prop yet; toggle icon on each play click.
        icon = self.play_button.get_icon_name()
        if icon == "media-playback-start-symbolic":
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
        self.engine.set_property("hdri-file", filepath)
        self.engine.set_property("hdri-skybox", True)

    def create_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        return action

    @Gtk.Template.Callback("enum_name")
    def enum_name (self, item):
        return item.get_nick().title().replace("-", " ")

    @Gtk.Template.Callback("on_close_request")
    def on_close_request(self, window):
        log.debug("window closed, saving settings")
        prepared = getattr(self, "_prepared_load_path", None)
        if prepared:
            release_prepared(prepared)
            self._prepared_load_path = None
        settings.set_int(
            "startup-width", window.get_width())
        settings.set_int(
            "startup-height", window.get_height())
        settings.set_boolean(
            "startup-sidebar-show", window.split_view.get_show_sidebar())
        settings.set_boolean(
            "auto-best", settings.get_boolean("auto-best"))
