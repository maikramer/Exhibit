# SPDX-License-Identifier: GPL-3.0-or-later
"""Save-image / toast helpers extracted from Viewer3dWindow."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, GLib, Gtk


class ExportMixin:
    """PNG export dialog and toast helpers."""

    def send_toast(self, message, timeout=2):
        toast = Adw.Toast(title=message, timeout=timeout)
        self.toast_overlay.add_toast(toast)

    def save_as_image(self, filepath):
        img = self.f3d_viewer.render_image()
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
                title=_("Image Saved"),
                timeout=2,
                button_label=_("Open"),
                action_name="app.show-image-externally",
                action_target=GLib.Variant("s", file_path)
            )
            self.toast_overlay.add_toast(toast)

