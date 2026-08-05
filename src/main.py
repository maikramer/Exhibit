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

from gi.repository import Gtk, Gio, Adw, GLib
from . import logger_lib
from .window import ExbWindow

from gettext import gettext as _


class ExhibitApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        logger_lib.init()
        super().__init__(
            application_id="io.github.nokse22.Exhibit",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.logger = logger_lib.logger

        self.lib_info = "" #f3d.Engine.get_lib_info()
        # self.backends = f3d.Engine.get_rendering_backend_list()

        self.create_action("quit", lambda *_: self.quit(), ["<primary>q"])
        self.create_action("about", self.on_about_action)
        self.create_action("help", self.on_help_action, ["F1"])
        # shortcuts-dialog.ui lists app.open-preferences; forward to the window.
        self.create_action(
            "open-preferences",
            self.on_open_preferences,
            ["<primary>comma"],
        )

        self.create_action("open-hdri-folder", self.on_open_hdri_folder)
        self.create_action("open-configs-folder", self.on_open_configs_folder)

        self.create_action(
            "open-new-window",
            lambda *_: ExbWindow(application=self).present(),
            ["<primary><shift>n"],
        )
        self.create_action(
            "open-external",
            self.on_open_external,
            ["<primary><shift>e"],
        )

        user_home_dir = (
            os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~")
        )
        show_image_external_action = Gio.SimpleAction.new_stateful(
            "show-image-externally",
            GLib.VariantType.new("s"),
            GLib.Variant("s", user_home_dir),
        )
        show_image_external_action.connect("activate", self.show_image_external)
        self.add_action(show_image_external_action)

        self.saved_settings = Gio.Settings.new("io.github.nokse22.Exhibit")

        theme = self.saved_settings.get_string("theme")
        if theme in ("default", "follow"):
            theme = "auto"
        if theme not in ("auto", "light", "dark"):
            theme = "auto"
        theme_action = Gio.SimpleAction.new_stateful(
            "theme",
            GLib.VariantType.new("s"),
            GLib.Variant("s", theme),
        )
        theme_action.connect("activate", self.on_theme_setting_changed)
        theme_action.connect("change-state", self.on_theme_setting_changed)
        self.add_action(theme_action)
        self.update_theme()

    def on_theme_setting_changed(self, action, state):
        if state is None:
            return
        value = state.get_string()
        if value in ("default", "follow"):
            value = "auto"
        if value not in ("auto", "light", "dark"):
            return
        action.set_state(GLib.Variant("s", value))
        self.saved_settings.set_string("theme", value)
        self.update_theme()

    def update_theme(self):
        manager = Adw.StyleManager.get_default()
        match self.saved_settings.get_string("theme"):
            case "auto" | "follow" | "default":
                manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
            case "light":
                manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            case "dark":
                manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            case _:
                manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def do_open(self, files, n_files, hint):
        paths = []
        for i in range(n_files):
            path = files[i].get_path()
            if path:
                paths.append(path)
        if not paths:
            return
        win = self.props.active_window
        if win is None:
            win = ExbWindow(application=self, startup_filepath=paths[0])
            win.present()
            # Rest join the sequential open queue (warm-load / realize safe).
            if len(paths) > 1:
                win._open_model_paths(paths[1:])
            return
        win.present()
        win._open_model_paths(paths)

    def show_image_external(self, _action, image_path: GLib.Variant, *args):
        try:
            image_file = Gio.File.new_for_path(image_path.get_string())
        except Exception as e:
            self.logger.error("show-image-externally path: %s", e)
            return
        launcher = Gtk.FileLauncher.new(image_file)

        def open_image_finish(_, result, *args):
            try:
                launcher.launch_finish(result)
            except Exception as e:
                self.logger.error("show-image-externally launch: %s", e)

        launcher.launch(self.props.active_window, None, open_image_finish)

    def on_about_action(self, *args):
        from .about_info import FORK_ISSUES, FORK_REPO, about_comments

        about = Adw.AboutDialog(
            application_name="Exhibit",
            application_icon="io.github.nokse22.Exhibit",
            developer_name="Nokse",
            version=self.get_version() if hasattr(self, "get_version") else "1.9.2",
            website=FORK_REPO,
            issue_url=FORK_ISSUES,
            developers=["Nokse", "maikramer (fork)"],
            license_type="GTK_LICENSE_GPL_3_0",
            copyright="© 2024-2026 Nokse",
            artists=["Jakub Steiner https://jimmac.eu"],
            comments=about_comments(),
        )

        about.add_link(_("Checkout F3D"), "https://f3d.app")
        about.add_link(_("Upstream Exhibit"), "https://github.com/Nokse22/Exhibit")

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
            # + f"F3D Version: {self.lib_info.version_full}\n"
            # + f"Build Date: {self.lib_info.build_date}\n"
            # + f"Build System: {self.lib_info.build_system}\n"
            # + f"VTK Version: {self.lib_info.vtk_version}\n"
            # + f"F3D License: {self.lib_info.license}\n"
            # + "\n"
            # + f"Modules:\n{'\n'.join([f'- {key}: {val}' for key, val in self.lib_info.modules.items()])}\n"
            # + f"Backends:\n{'\n'.join([f'- {key}: {val}' for key, val in self.backends.items()])}"
            # + f"\nF3D Copyrights:\n- {'\n- '.join(self.lib_info.copyrights)}\n"
        )

        about.present(self.props.active_window)

    def on_help_action(self, *args):
        # Flatpak / host without yelp help:exhibit → fall back to upstream docs.
        try:
            ok = Gio.AppInfo.launch_default_for_uri("help:exhibit")
        except Exception as exc:
            self.logger.debug("help:exhibit: %s", exc)
            ok = False
        if ok:
            return
        try:
            Gio.AppInfo.launch_default_for_uri(
                "https://github.com/Nokse22/Exhibit"
            )
        except Exception as exc:
            self.logger.debug("help fallback URL: %s", exc)

    def on_open_preferences(self, *_args):
        win = self.props.active_window
        if win is None:
            return
        open_prefs = getattr(win, "on_preferences_clicked", None)
        if callable(open_prefs):
            open_prefs()

    def on_open_hdri_folder(self, *_args):
        win = self.props.active_window
        path = getattr(win, "hdri_path", None) if win is not None else None
        if path:
            webbrowser.open(path)

    def on_open_configs_folder(self, *_args):
        win = self.props.active_window
        path = getattr(win, "configs_path", None) if win is not None else None
        if path:
            webbrowser.open(path)

    def on_open_external(self, *_args):
        win = self.props.active_window
        if win is None:
            return
        open_ext = getattr(win, "open_with_external_app", None)
        if callable(open_ext):
            open_ext()

    def do_startup(self):
        Adw.Application.do_startup(self)
        # Adw ≥1.8 auto-wires app.shortcuts from shortcuts-dialog.ui; older
        # libadwaita (or failed resource load) leaves the menu item dead.
        if self.lookup_action("shortcuts") is None:
            self.create_action(
                "shortcuts",
                self.on_shortcuts_action,
                ["<primary>question"],
            )

    def on_shortcuts_action(self, *_args):
        try:
            builder = Gtk.Builder.new_from_resource(
                "/io/github/nokse22/Exhibit/shortcuts-dialog.ui"
            )
        except GLib.Error as exc:
            logger_lib.logger.debug("shortcuts dialog resource: %s", exc)
            return
        dialog = builder.get_object("shortcuts_dialog")
        if dialog is None:
            return
        dialog.present(self.props.active_window)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            # File opens go through do_open (HANDLES_OPEN); activate is empty window.
            win = ExbWindow(application=self)
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
    app = ExhibitApplication()
    return app.run(sys.argv)
