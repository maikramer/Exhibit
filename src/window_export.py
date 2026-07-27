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

    def save_as_image(self, filepath) -> bool:
        img = self.f3d_viewer.render_image()
        if img is None:
            self.send_toast(_("Could not save image"))
            return False
        try:
            img.save(filepath)
        except Exception as exc:
            self.logger.error("save image failed: %s", exc)
            self.send_toast(_("Could not save image"))
            return False
        return True

    def open_save_file_chooser(self, *args):
        dialog = Gtk.FileDialog(
            title=_("Save File"),
            initial_name=self.file_name.split(".")[0] + ".png",
        )
        dialog.save(self, None, self.on_save_file_response)

    def on_save_file_response(self, dialog, response):
        try:
            file = dialog.save_finish(response)
        except Exception as exc:
            # User cancel is common; other failures stay in debug.
            self.logger.debug("save dialog finish: %s", exc)
            return

        if not file:
            return

        file_path = file.get_path()
        if not file_path:
            # Remote/URI-only locations have no local path; Pillow needs one.
            self.send_toast(_("Could not save image"))
            return

        if not self.save_as_image(file_path):
            return
        toast = Adw.Toast(
            title=_("Image Saved"),
            timeout=2,
            button_label=_("Open"),
            action_name="app.show-image-externally",
            action_target=GLib.Variant("s", file_path)
        )
        self.toast_overlay.add_toast(toast)

