# main.py
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

import sys
import os
import webbrowser

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Gdk, Gio, Adw, GLib

GLib.setenv("GDK_DEBUG", "gl-prefer-gl", True)

import f3d

from .window import Viewer3dWindow
from . import logger_lib

from gettext import gettext as _

_STYLE_RESOURCE = "/io/github/nokse22/Exhibit/style.css"
_STYLE_DARK_RESOURCE = "/io/github/nokse22/Exhibit/style-dark.css"


class Viewer3dApplication(Adw.Application):
    """The main application singleton class."""

    open_filepath = None

    def __init__(self):
        super().__init__(
            application_id="io.github.nokse22.Exhibit",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )

        logger_lib.init()

        self.lib_info = f3d.Engine.get_lib_info()
        self.backends = f3d.Engine.get_rendering_backend_list()

        self._css_provider = None
        self._dark_css_provider = None
        self._css_loaded = False

        self.create_action("quit", lambda *_: self.quit(), ["<primary>q"])
        self.create_action("about", self.on_about_action)
        self.create_action("help", self.on_help_action, ["F1"])

        self.create_action(
            "open-hdri-folder",
            lambda *_: webbrowser.open(self.props.active_window.hdri_path),
        )
        self.create_action(
            "open-configs-folder",
            lambda *_: webbrowser.open(self.props.active_window.configs_path),
        )

        self.create_action(
            "open-new-window",
            lambda *_: Viewer3dWindow(application=self).present(),
            ["<primary><shift>n"],
        )
        self.create_action(
            "open-external",
            lambda *_: self.props.active_window.open_with_external_app(),
            ["<primary><shift>e"],
        )

        user_home_dir = os.environ.get("XDG_CONFIG_HOME", os.environ["HOME"])
        show_image_external_action = Gio.SimpleAction.new_stateful(
            "show-image-externally",
            GLib.VariantType.new("s"),
            GLib.Variant("s", user_home_dir),
        )
        show_image_external_action.connect("activate", self.show_image_external)
        self.add_action(show_image_external_action)

        self.saved_settings = Gio.Settings.new("io.github.nokse22.Exhibit")

        theme_action = Gio.SimpleAction.new_stateful(
            "theme",
            GLib.VariantType.new("s"),
            GLib.Variant("s", self.saved_settings.get_string("theme")),
        )
        theme_action.connect("activate", self.on_theme_setting_changed)
        self.update_theme()
        self.add_action(theme_action)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._load_css()

    def _load_css(self):
        if self._css_loaded:
            return

        display = Gdk.Display.get_default()
        if display is None:
            return

        self._css_provider = Gtk.CssProvider()
        self._css_provider.load_from_resource(_STYLE_RESOURCE)
        Gtk.StyleContext.add_provider_for_display(
            display,
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._dark_css_provider = Gtk.CssProvider()
        self._dark_css_provider.load_from_resource(_STYLE_DARK_RESOURCE)

        style_manager = Adw.StyleManager.get_default()
        style_manager.connect("notify::dark", self._on_dark_changed)
        self._on_dark_changed(style_manager)
        self._css_loaded = True

    def _on_dark_changed(self, style_manager, *_args):
        display = Gdk.Display.get_default()
        if display is None or self._dark_css_provider is None:
            return

        if style_manager.get_dark():
            Gtk.StyleContext.add_provider_for_display(
                display,
                self._dark_css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
            )
        else:
            Gtk.StyleContext.remove_provider_for_display(
                display, self._dark_css_provider
            )

    def do_open(self, files, n_files, hint):
        win = self.props.active_window
        if win is None:
            first = files[0].get_path() if n_files else None
            win = Viewer3dWindow(application=self, startup_filepath=first)
            win.present()
            # Remaining files open as extra tabs.
            for i in range(1, n_files):
                path = files[i].get_path()
                if path:
                    win.load_file(filepath=path)
            return
        win.present()
        for i in range(n_files):
            path = files[i].get_path()
            if path:
                win.load_file(filepath=path)

    def show_image_external(self, _action, image_path: GLib.Variant, *args):
        try:
            image_file = Gio.File.new_for_path(image_path.get_string())
        except Exception as e:
            self.logger.error(e)
        else:
            launcher = Gtk.FileLauncher.new(image_file)

            def open_image_finish(_, result, *args):
                try:
                    launcher.launch_finish(result)
                except Exception as e:
                    self.logger.error(e)

            launcher.launch(self.props.active_window, None, open_image_finish)

    def on_about_action(self, *args):
        about = Adw.AboutDialog(
            application_name="Exhibit",
            application_icon="io.github.nokse22.Exhibit",
            developer_name="Nokse",
            version="1.6.0",
            website="https://github.com/Nokse22/Exhibit",
            issue_url="https://github.com/Nokse22/Exhibit/issues",
            developers=["Nokse"],
            license_type="GTK_LICENSE_GPL_3_0",
            copyright="© 2024-2025 Nokse",
            artists=["Jakub Steiner https://jimmac.eu"],
        )

        about.add_link(_("Checkout F3D"), "https://f3d.app")

        about.add_link(_("Donate with Ko-Fi"), "https://ko-fi.com/nokse22")
        about.add_link(_("Donate with Github"), "https://github.com/sponsors/Nokse22")

        about.set_debug_info(
            f"GDK_DEBUG: {GLib.getenv('GDK_DEBUG')}\n"
            + f"GSK_RENDERER: {GLib.getenv('GSK_RENDERER')}\n"
            + f"DISPLAY: {GLib.getenv('DISPLAY')}\n"
            + f"XDG_SESSION_TYPE: {GLib.getenv('XDG_SESSION_TYPE')}\n"
            + f"XDG_SESSION_DESKTOP: {GLib.getenv('XDG_SESSION_DESKTOP')}\n"
            + f"GTK_THEME: {GLib.getenv('GTK_THEME')}\n"
            + f"GTK Version: {Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}.{Gtk.MICRO_VERSION}\n"
            + "\n"
            + f"F3D Version: {self.lib_info.version_full}\n"
            + f"Build Date: {self.lib_info.build_date}\n"
            + f"Build System: {self.lib_info.build_system}\n"
            + f"VTK Version: {self.lib_info.vtk_version}\n"
            + f"F3D License: {self.lib_info.license}\n"
            + "\n"
            + f"Modules:\n{'\n'.join([f'- {key}: {val}' for key, val in self.lib_info.modules.items()])}\n"
            + f"Backends:\n{'\n'.join([f'- {key}: {val}' for key, val in self.backends.items()])}"
            + f"\nF3D Copyrights:\n- {'\n- '.join(self.lib_info.copyrights)}\n"
        )

        about.present(self.props.active_window)

    def on_help_action(self, *args):
        Gio.AppInfo.launch_default_for_uri("help:exhibit")

    def on_theme_setting_changed(self, action, state):
        action.set_state(state)
        self.saved_settings.set_string("theme", state.get_string())
        self.update_theme()

    def update_theme(self):
        # DEFAULT = follow OS (portal): Ubuntu prefer-dark + accent (Yaru orange).
        manager = Adw.StyleManager.get_default()
        match self.saved_settings.get_string("theme"):
            case "follow":
                manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
            case "light":
                manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            case "dark":
                manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            if self.open_filepath:
                win = Viewer3dWindow(
                    application=self, startup_filepath=self.open_filepath
                )
            else:
                win = Viewer3dWindow(application=self)
        win.present()

    def create_action(self, name, callback, shortcuts=None, *args):
        action = Gio.SimpleAction.new(name, None)
        if args:
            action.connect("activate", callback, *args)
        else:
            action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version):
    """The application's entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "render":
        from . import cli_render

        return cli_render.main(sys.argv[2:])

    app = Viewer3dApplication()
    return app.run(sys.argv)
