# SPDX-License-Identifier: GPL-3.0-or-later
"""File open / warm-load / drop helpers extracted from Viewer3dWindow."""

from __future__ import annotations

import os
import re
import threading

from gettext import gettext as _, ngettext
from gi.repository import Adw, Gio, GLib, Gtk

from .drop_paths import DEFAULT_MAX_BATCH_OPEN, collect_openable_model_paths
from .meshopt_decompress import (
    MeshoptError,
    cleanup_decompressed,
    prepare_glb_for_load,
    release_prepared,
)
from .open_errors import format_open_failure_message
from .path_utils import resolve_readable_path
from .recent_files import clear_recent, existing_recent, push_recent
from .session_files import (
    collect_session_paths,
    session_paths_to_restore,
)
from .warm_load import new_warm_load_holder
from .widgets import ViewerTab
from .file_patterns import allowed_extensions, image_patterns


class LoadMixin:
    """Chooser, drop, warm-load and open/error UX for ``Viewer3dWindow``."""

    def open_file_chooser(self, *args):
        file_filter = Gtk.FileFilter(name=_("All supported formats"))

        for patt in allowed_extensions:
            file_filter.add_pattern("*." + patt)

        filter_list = Gio.ListStore.new(Gtk.FileFilter())
        filter_list.append(file_filter)

        dialog = Gtk.FileDialog(
            title=_("Open File"),
            filters=filter_list)

        dialog.open_multiple(self, None, self.on_open_files_response)

    def open_folder_chooser(self, *args):
        dialog = Gtk.FileDialog(title=_("Open Folder"))
        dialog.select_folder(self, None, self.on_open_folder_response)

    def on_open_folder_response(self, dialog, response):
        try:
            folder = dialog.select_folder_finish(response)
        except Exception as exc:
            self.logger.error("Exception opening folder: %s", exc)
            return
        if folder is None:
            return
        folder_path = folder.get_path()
        if not folder_path:
            self.on_file_not_opened(folder.get_basename() or _("Unknown"))
            return
        model_paths = collect_openable_model_paths(
            [folder_path], allowed_exts=allowed_extensions
        )
        if not model_paths:
            self.send_toast(
                _("No supported models in {}").format(
                    os.path.basename(folder_path) or folder_path
                ),
                timeout=4,
            )
            return
        self.logger.info(
            "open folder response (%d model(s))", len(model_paths)
        )
        self._open_model_paths(model_paths)

    def _open_model_paths(self, model_paths: list[str]) -> None:
        """Open models sequentially; first uses default tab logic, rest queue.

        Warm loads need the target tab mapped so its GLArea can realize.
        Starting them all at once selects only the last tab — earlier tabs
        never realize and stay stuck on the loading page forever, so each
        next open only starts when the previous load settles.
        """
        total = len(model_paths)
        limit = DEFAULT_MAX_BATCH_OPEN
        if total > limit:
            self.send_toast(
                _("Opening first {} of {} models").format(limit, total),
                timeout=4,
            )
            model_paths = model_paths[:limit]
        if not model_paths:
            return
        self._pending_open_paths = list(model_paths[1:])
        self.load_file(filepath=model_paths[0])

    def _advance_open_queue(self) -> bool:
        """Start the next queued model open; True when one was started."""
        pending = getattr(self, "_pending_open_paths", None)
        if not pending:
            return False
        next_path = pending.pop(0)
        self.load_file(filepath=next_path, new_tab=True)
        return True

    def on_open_files_response(self, dialog, response):
        try:
            files = dialog.open_multiple_finish(response)
        except Exception as e:
            self.logger.error(f"Exception Opening file: {e}")
            return

        if not files:
            return
        paths: list[str] = []
        for i in range(files.get_n_items()):
            file = files.get_item(i)
            filepath = file.get_path() if file else None
            if not filepath:
                self.logger.error("Opened file has no local path")
                self.on_file_not_opened(
                    file.get_basename() if file else _("Unknown"))
                continue
            paths.append(filepath)
        if not paths:
            return
        self.logger.info("open file response (%d path(s))", len(paths))
        # Folders selected via multi-open are expanded like a drop.
        model_paths = collect_openable_model_paths(
            paths, allowed_exts=allowed_extensions
        )
        if model_paths:
            self._open_model_paths(model_paths)
            return
        for filepath in paths:
            self.load_file(filepath=filepath)

    def load_file(self, **kwargs):
        tab_hint = kwargs.get("_tab")
        filepath = kwargs.get("filepath")
        if not filepath and isinstance(tab_hint, ViewerTab):
            filepath = tab_hint.filepath
        if not filepath:
            filepath = self.filepath
        kwargs["filepath"] = filepath

        if filepath:
            basename = os.path.basename(filepath)
        elif isinstance(tab_hint, ViewerTab) and tab_hint.file_name:
            basename = tab_hint.file_name
        elif self.file_name:
            basename = self.file_name
        else:
            basename = _("Untitled")

        replace = kwargs.get("override") or kwargs.get("preserve_orientation")
        new_tab = kwargs.get("new_tab")
        if new_tab is None:
            # First document reuses the empty tab; later opens get a new tab.
            new_tab = (not replace) and (not self.no_file_loaded)

        if new_tab:
            # Prepare tab in background; same startup loading_page as first open.
            tab = self._add_viewer_tab(title=basename, select=False)
            page = self._tab_page(tab)
            if page is not None:
                page.set_loading(True)
                page.set_title(basename)
        else:
            tab = tab_hint if isinstance(tab_hint, ViewerTab) else self._active_tab()
            if tab is None:
                tab = self._add_viewer_tab(title=basename, select=True)
            if not tab.file_name:
                tab.file_name = basename
            page = self._tab_page(tab)
            if page is not None:
                page.set_loading(True)
                self._refresh_tab_title(tab)

        kwargs["_tab"] = tab
        # Extra tabs inherit current preset — skip auto-best churn.
        kwargs["_skip_auto_best"] = bool(new_tab)
        self._update_tab_bar_visibility()

        # Keep 3d_page mapped so the tab GLArea can realize — F3D
        # create_external needs a current Gtk GL context. Full-page
        # startup loading unmaps the viewer and makes init impossible.
        self.loading_label.set_label(_("Loading {}").format(basename))
        self.stack.set_visible_child_name("3d_page")

        tab.stats_overlay_label.set_visible(False)
        self.block_reload = True

        # Fresh opens start in bind pose; reloads keep the selected clip.
        if not kwargs.get("override") and not kwargs.get("preserve_orientation"):
            self.window_settings.set_setting("animation-index", None, False)
            tab.viewer.update_options({"animation-index": None}, queue_render=False)

        # Capture camera on the main thread before async prepare.
        if kwargs.get("preserve_orientation") and tab.viewer.engine is not None:
            try:
                kwargs["_camera_state"] = tab.viewer.get_camera_state()
            except Exception as exc:
                self.logger.debug("preserve camera state failed: %s", exc)
                kwargs["_camera_state"] = None

        # Always prepare off-main; scene.add only on main (GL-safe).
        self._start_warm_load(tab, kwargs)

    @staticmethod
    def _resolve_readable_path(filepath: str) -> str | None:
        """Return a path the sandbox can read (follow home→/media symlinks)."""
        return resolve_readable_path(filepath)

    def _start_warm_load(self, tab: ViewerTab, kwargs: dict):
        """Overlap GLB prepare (worker) with F3D engine create (main)."""
        # Replace any prior in-flight prepare for this tab.
        self._cancel_warm_load(tab)

        filepath = kwargs.get("filepath")
        holder = new_warm_load_holder()
        tab._warm_load_holder = holder

        def prepare_worker():
            try:
                if not filepath:
                    raise ValueError("missing filepath")
                resolved = self._resolve_readable_path(filepath)
                if resolved is None:
                    raise FileNotFoundError(filepath)
                load_path, meshopt_temp = prepare_glb_for_load(resolved)
                holder["ok"] = (resolved, load_path, meshopt_temp)
            except Exception as exc:
                holder["err"] = exc
                holder["path"] = filepath
            holder["ready"] = True
            # Tab may have closed while prepare ran — free temps here because
            # the GLib tick will only see cancelled and exit.
            if holder.get("cancelled"):
                self._release_warm_holder_temps(holder)

        # Map the target tab so its GLArea can realize during prepare.
        self.stack.set_visible_child_name("3d_page")
        page = self._tab_page(tab)
        if page is not None and self.tab_view.get_selected_page() != page:
            self._switching_tab = True
            self.tab_view.set_selected_page(page)
            self._switching_tab = False

        threading.Thread(target=prepare_worker, daemon=True).start()
        # Single poller: wait for realize + prepare, then load once.
        GLib.timeout_add(16, self._warm_load_tick, tab, kwargs, holder)

    def _warm_load_tick(self, tab: ViewerTab, kwargs: dict, holder: dict):
        """Advance warm load when prepare and GL context are both ready."""
        if holder.get("cancelled"):
            self._release_warm_holder_temps(holder)
            if tab._warm_load_holder is holder:
                tab._warm_load_holder = None
            return GLib.SOURCE_REMOVE
        if holder.get("finished"):
            return GLib.SOURCE_REMOVE

        viewer = tab.viewer
        try:
            if viewer.engine is None:
                if not viewer.get_realized():
                    # First open still shows startup loading; flip to 3d so
                    # the GLArea can map, then keep polling for realize.
                    if self.stack.get_visible_child_name() != "3d_page":
                        self.stack.set_visible_child_name("3d_page")
                    return GLib.SOURCE_CONTINUE
                viewer.initialize()
        except Exception as exc:
            holder["cancelled"] = True
            self.logger.error(f"F3D init failed: {exc}")
            path = kwargs.get("filepath")
            self._release_warm_holder_temps(holder)
            if tab._warm_load_holder is holder:
                tab._warm_load_holder = None
            self.on_file_not_opened(path, tab)
            return GLib.SOURCE_REMOVE

        if not holder.get("ready"):
            return GLib.SOURCE_CONTINUE

        if "err" in holder:
            holder["finished"] = True
            if tab._warm_load_holder is holder:
                tab._warm_load_holder = None
            err = holder["err"]
            path = holder.get("path") or kwargs.get("filepath")
            self.logger.error(f"Warm prepare failed: {err}")
            self.on_file_not_opened(path, tab, reason=err)
            return GLib.SOURCE_REMOVE

        holder["finished"] = True
        if tab._warm_load_holder is holder:
            tab._warm_load_holder = None
        try:
            self._warm_prepare_finished(tab, kwargs, holder)
        except Exception as exc:
            self.logger.error(f"Warm load failed: {exc}")
            path = kwargs.get("filepath")
            self._release_warm_holder_temps(holder)
            self.on_file_not_opened(path, tab)
        return GLib.SOURCE_REMOVE

    def _warm_prepare_finished(self, tab: ViewerTab, kwargs: dict, holder: dict):
        if holder.get("cancelled"):
            self._release_warm_holder_temps(holder)
            return GLib.SOURCE_REMOVE
        if holder.get("_temps_released"):
            return GLib.SOURCE_REMOVE

        if "err" in holder:
            err = holder["err"]
            path = holder.get("path") or kwargs.get("filepath")
            self.logger.error(f"Warm prepare failed: {err}")
            self.on_file_not_opened(path, tab, reason=err)
            return GLib.SOURCE_REMOVE

        filepath, load_path, meshopt_temp = holder["ok"]
        viewer = tab.viewer
        if viewer.engine is None:
            viewer.initialize()

        override = kwargs.get("override", False)
        add_file = kwargs.get("add_file", False)
        skip_auto_best = kwargs.get("_skip_auto_best", False)
        preserve_orientation = kwargs.get("preserve_orientation", False)
        camera_state = kwargs.get("_camera_state")

        self.change_checker.stop()

        if (not skip_auto_best
                and self.window_settings.get_setting("auto-best").value
                and not override and not add_file):
            self.logger.debug("choosing best settings")
            settings = "general"
            for key, value in self.configurations.items():
                pattern = value["formats"]
                if pattern == ".*()":
                    continue
                if re.search(pattern, filepath):
                    settings = key
            self.logger.debug(f"best settings is {settings}")
            self.change_setting_state(GLib.Variant("s", settings))

        try:
            if holder.get("cancelled"):
                self._release_warm_holder_temps(holder)
                return GLib.SOURCE_REMOVE
            if not viewer.supports(load_path):
                holder["_temps_released"] = True
                if load_path != filepath:
                    release_prepared(load_path)
                self.on_file_not_opened(filepath, tab)
                return GLib.SOURCE_REMOVE
            if add_file:
                ok = viewer.add_file(filepath, prepared_path=load_path)
            else:
                ok = viewer.load_file(filepath, prepared_path=load_path)
            # Success: viewer owns prepared path. Failure: viewer already
            # released (or never retained). Either way, cancel must not
            # release_prepared again.
            holder["_temps_released"] = True
            if not ok:
                self.on_file_not_opened(filepath, tab)
                return GLib.SOURCE_REMOVE
        except Exception as exc:
            self.logger.error(f"Error while loading into viewer: {exc}")
            holder["_temps_released"] = True
            if load_path != filepath:
                release_prepared(load_path)
            self.on_file_not_opened(filepath, tab)
            return GLib.SOURCE_REMOVE
        finally:
            cleanup_decompressed(meshopt_temp)

        if preserve_orientation and camera_state is not None:
            try:
                viewer.set_camera_state(camera_state)
            except Exception as exc:
                self.logger.debug("preserve camera restore failed: %s", exc)

        tab.filepath = filepath
        tab.file_name = os.path.basename(filepath)
        self.on_file_opened(tab)
        return GLib.SOURCE_REMOVE

    def _remember_recent_file(self, filepath: str | None) -> None:
        if not filepath or not os.path.isfile(filepath):
            return
        current = list(self.saved_settings.get_strv("recent-files"))
        updated = push_recent(current, filepath)
        if updated != current:
            self.saved_settings.set_strv("recent-files", updated)
        self._refresh_recent_files_ui()

    def _persist_session_files(self) -> None:
        if not self.saved_settings.get_boolean("restore-session"):
            return
        # Mid-batch (e.g. session restore) tabs still loading have no
        # filepath yet — persisting now would truncate the stored session.
        if getattr(self, "_pending_open_paths", None):
            return
        if any(
            getattr(tab, "_warm_load_holder", None) is not None
            for tab in self._iter_tabs()
        ):
            return
        paths = collect_session_paths(
            [tab.filepath for tab in self._iter_tabs()]
        )
        current = list(self.saved_settings.get_strv("session-files"))
        if paths != current:
            self.saved_settings.set_strv("session-files", paths)

    def _restore_session_files(self) -> None:
        enabled = self.saved_settings.get_boolean("restore-session")
        stored = list(self.saved_settings.get_strv("session-files"))
        paths = session_paths_to_restore(enabled, stored)
        if enabled and paths != stored:
            self.saved_settings.set_strv("session-files", paths)
        if not paths:
            return
        count = len(paths)
        self.logger.info("restoring session (%d model(s))", count)
        self.send_toast(
            ngettext(
                "Restoring {} model from last session",
                "Restoring {} models from last session",
                count,
            ).format(count),
            timeout=3,
        )
        self._open_model_paths(paths)

    def _refresh_recent_files_ui(self) -> None:
        while True:
            child = self.recent_files_list.get_first_child()
            if child is None:
                break
            self.recent_files_list.remove(child)

        stored = list(self.saved_settings.get_strv("recent-files"))
        paths = existing_recent(stored)
        if paths != stored:
            # Drop missing paths so GSettings stays tidy.
            self.saved_settings.set_strv("recent-files", paths)
        self.recent_files_box.set_visible(bool(paths))
        for path in paths:
            row = Adw.ActionRow(
                title=os.path.basename(path),
                subtitle=path,
                activatable=True,
            )
            row.connect("activated", self._on_recent_file_activated, path)
            self.recent_files_list.append(row)

    def _on_recent_file_activated(self, _row, path: str) -> None:
        if not os.path.isfile(path):
            self._refresh_recent_files_ui()
            self.on_file_not_opened(os.path.basename(path) or _("Unknown"))
            return
        self.load_file(filepath=path)

    @Gtk.Template.Callback("on_clear_recent_clicked")
    def on_clear_recent_clicked(self, *_args) -> None:
        self.saved_settings.set_strv("recent-files", clear_recent())
        self._refresh_recent_files_ui()

    def on_file_opened(self, tab=None):
        self.logger.debug("on file opened")
        tab = tab or self._active_tab()
        if tab is None:
            self.block_reload = False
            return GLib.SOURCE_REMOVE

        page = self._tab_page(tab)
        if page is not None:
            page.set_loading(False)

        self.filepath = tab.filepath
        self.file_name = tab.file_name
        tab.loaded = True
        mtime = self._file_mtime(tab.filepath)
        if mtime is not None:
            tab.loaded_mtime = mtime
            tab.seen_disk_mtime = mtime
        tab.externally_modified = False
        if page is not None:
            self._configure_tab_page(page, tab)

        # Reveal the ready tab (may have been prepared off-screen).
        if page is not None and self.tab_view.get_selected_page() != page:
            self._switching_tab = True
            self.tab_view.set_selected_page(page)
            self._switching_tab = False
        self._bind_animation_controls(tab.viewer)

        self.no_file_loaded = False
        # Reveal tab bar only once the 2nd+ model is ready.
        chrome_changed = self._update_tab_bar_visibility()

        self.update_time_stamp()
        self.change_checker.run()

        self.set_title(_("Exhibit - {}").format(self.file_name))
        self.title_widget.set_subtitle(self.file_name)
        self.stack.set_visible_child_name("3d_page")
        tab.viewer.grab_focus()

        self.update_background_color()
        self._remember_recent_file(tab.filepath)
        self._persist_session_files()
        self._advance_open_queue()

        self.block_reload = False
        # Paint model first; sidebar extras can wait one idle tick.
        GLib.idle_add(self._post_open_sidebar_refresh)

        # Fit sooner when chrome already stable (3rd+ tab).
        GLib.timeout_add(120 if chrome_changed else 30, tab.viewer.done)
        return GLib.SOURCE_REMOVE

    def _post_open_sidebar_refresh(self):
        self.refresh_animation_combo()
        self.refresh_object_tree()
        self._refresh_mesh_stats()
        self._refresh_skin_weights_joint_combo()
        if self.window_settings.get_setting("stats-overlay").value:
            self._apply_stats_overlay(True)
        if self.window_settings.get_setting("skin-weights").value:
            self._apply_skin_weights_mode(True)
        return GLib.SOURCE_REMOVE

    def on_file_not_opened(self, filepath, tab=None, reason=None):
        self.logger.debug("on file not opened")
        tab = tab or self._active_tab()
        if tab is not None:
            page = self._tab_page(tab)
            if page is not None:
                page.set_loading(False)
            # Close a failed newly-created empty tab when other files remain.
            if not tab.loaded and self.tab_view.get_n_pages() > 1:
                if page is not None:
                    self.tab_view.close_page(page)
            else:
                tab.clear_overlays()
                tab.mesh_stats = None

        message = format_open_failure_message(
            filepath,
            reason,
            meshopt_error_type=MeshoptError,
            unknown_label=_("Unknown"),
            prepare_fmt=_("Can't prepare {}: {}"),
            open_reason_fmt=_("Can't open {}: {}"),
            open_fmt=_("Can't open {}"),
        )

        if self.no_file_loaded:
            self.set_title(_("Exhibit"))
            self.stack.set_visible_child_name("startup_page")
            self.startup_stack.set_visible_child_name("error_page")
            try:
                self.error_status_page.set_description(message)
            except Exception as exc:
                self.logger.debug("error_status_page update failed: %s", exc)
            # Still toast so packed-GLB prepare failures are readable.
            self.send_toast(message, timeout=5)
        else:
            # Return to the viewer; toast explains the failed open.
            self.stack.set_visible_child_name("3d_page")
            self.send_toast(message, timeout=5)

        self.update_background_color()
        self.refresh_object_tree()
        self._mesh_stats = None
        self._update_tab_bar_visibility()

        self.block_reload = False
        # A failed batch item must not stall the remaining queued opens.
        self._advance_open_queue()
        return GLib.SOURCE_REMOVE

    @Gtk.Template.Callback("on_open_button_clicked")
    def on_open_button_clicked(self, btn):
        self.open_file_chooser()

    @Gtk.Template.Callback("on_drop_received")
    def on_drop_received(self, drop, value, x, y):
        local_paths: list[str] = []
        for dropped in value.get_files():
            filepath = dropped.get_path()
            if not filepath:
                self.logger.error("Dropped file has no local path")
                continue
            local_paths.append(filepath)

        if not local_paths:
            self.on_file_not_opened(_("Unknown"))
            return

        # Single HDRI/image drop keeps the previous skybox behaviour.
        if len(local_paths) == 1 and os.path.isfile(local_paths[0]):
            extension = os.path.splitext(local_paths[0])[1][1:].lower()
            if extension in image_patterns:
                self.load_hdri(local_paths[0])
                return

        model_paths = collect_openable_model_paths(
            local_paths, allowed_exts=allowed_extensions
        )
        if not model_paths:
            name = os.path.basename(local_paths[0]) or _("Unknown")
            self.on_file_not_opened(name)
            return

        self.logger.info("drop received (%d model(s))", len(model_paths))
        self._open_model_paths(model_paths)

    @Gtk.Template.Callback("on_drop_enter")
    def on_drop_enter(self, drop_target, *args):
        drop_target.get_widget().set_visible_child_name("drop")

    @Gtk.Template.Callback("on_drop_leave")
    def on_drop_leave(self, drop_target, *args):
        drop_target.get_widget().set_visible_child_name("content")

    def load_hdri(self, filepath):
        self.window_settings.set_setting("hdri-file", filepath)
        self.window_settings.set_setting("hdri-skybox", True)
        self.use_skybox_switch.set_active(True)
        self.hdri_file_row.set_filename(filepath)
        options = {
            "hdri-file": filepath,
            "hdri-skybox": True}
        self._update_all_viewers_options(options)
        self.check_for_options_change()

    def reload_file(self, pres_or=False):
        if self.block_reload:
            return
        tab = self._active_tab()
        path = (tab.filepath if tab else "") or self.filepath
        if not path:
            self.logger.warning("reload_file: no filepath on active tab")
            return
        self.logger.info(f"Reloading file: {path}")
        self.load_file(
            filepath=path,
            override=True,
            preserve_orientation=pres_or,
            new_tab=False,
            _tab=tab,
        )

