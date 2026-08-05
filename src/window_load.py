# SPDX-License-Identifier: GPL-3.0-or-later
"""File open / warm-load / drop helpers extracted from Viewer3dWindow."""

from __future__ import annotations

import os
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
from .settings_compare import formats_pattern_matches
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
        pending = list(getattr(self, "_pending_open_paths", None) or [])
        in_flight = bool(getattr(self, "block_reload", False)) or (
            hasattr(self, "_warm_load_in_flight") and self._warm_load_in_flight()
        )
        if in_flight or pending:
            # Mid-batch / mid-load: append — never drop the existing queue.
            self._pending_open_paths = pending + list(model_paths)
            self.logger.info(
                "queued %d model(s); pending now %d",
                len(model_paths),
                len(self._pending_open_paths),
            )
            return
        self._pending_open_paths = list(model_paths[1:])
        self.load_file(filepath=model_paths[0])

    def _advance_open_queue(self) -> bool:
        """Start the next queued model open; True when one was started."""
        pending = getattr(self, "_pending_open_paths", None)
        if not pending:
            return False
        next_path = pending.pop(0)
        # Background queue: do not steal focus when a prior tab finishes.
        self.load_file(
            filepath=next_path, new_tab=True, _auto_select_on_open=False
        )
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
        # Folders / unsupported picks: do not call load_file on raw paths.
        self.send_toast(_("No supported models in selection"), timeout=4)

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
        # Same file already open → focus + flash (default on; Loading setting).
        if (
            filepath
            and not replace
            and tab_hint is None
            and self.saved_settings.get_boolean("focus-existing-tab")
        ):
            existing = self._find_tab_by_filepath(filepath)
            if existing is not None:
                self._focus_existing_tab(existing)
                # Keep batch opens moving when a duplicate is skipped.
                if not self._advance_open_queue():
                    self._unblock_reload_if_idle()
                return

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
        # Batch queue sets False so finishing a background tab does not steal focus.
        tab._auto_select_on_open = bool(kwargs.get("_auto_select_on_open", True))
        self._update_tab_bar_visibility()

        # Keep 3d_page mapped so the tab GLArea can realize — F3D
        # create_external needs a current Gtk GL context. Full-page
        # startup loading unmaps the viewer and makes init impossible.
        loading_label = getattr(self, "loading_label", None)
        if loading_label is not None:
            loading_label.set_label(_("Loading {}").format(basename))
        status = getattr(self, "loading_status_page", None)
        if status is not None:
            try:
                status.set_title(_("Loading {}").format(basename))
            except Exception:
                pass
        self.stack.set_visible_child_name("3d_page")

        tab.stats_overlay_label.set_visible(False)
        self.block_reload = True

        # Fresh opens start in bind pose; reloads keep the selected clip.
        # Batch view so changed-no-ui-update does not stomp sibling tabs' clips.
        if not kwargs.get("override") and not kwargs.get("preserve_orientation"):
            tab.viewer.update_options({"animation-index": None}, queue_render=False)
            self.window_settings.begin_view_batch()
            try:
                self.window_settings.set_setting("animation-index", None, False)
            finally:
                self.window_settings.end_view_batch()

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

    def _warm_load_in_flight(self) -> bool:
        """True while any tab still has an unfinished warm-load holder."""
        for tab in self._iter_tabs():
            holder = getattr(tab, "_warm_load_holder", None)
            if not holder:
                continue
            if holder.get("cancelled") or holder.get("finished"):
                continue
            return True
        return False

    def _unblock_reload_if_idle(self) -> None:
        """Clear window-wide ``block_reload`` when no warm load remains."""
        if not self._warm_load_in_flight():
            self.block_reload = False

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
        # Batch opens still need a temporary select (GL realize); restore later.
        self.stack.set_visible_child_name("3d_page")
        page = self._tab_page(tab)
        prefer_select = bool(kwargs.get("_auto_select_on_open", True))
        prev_page = self.tab_view.get_selected_page()
        if page is not None and prev_page != page:
            if not prefer_select:
                holder["_restore_selected_page"] = prev_page
                tab._restore_selected_page = prev_page
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
            self._unblock_reload_if_idle()
            return GLib.SOURCE_REMOVE
        if holder.get("finished"):
            return GLib.SOURCE_REMOVE

        viewer = tab.viewer
        # Exb.Engine.load_file defers until View realize (scene NULL → stash file).
        # Must not treat that as "loaded" or on_file_opened races an empty viewport.
        try:
            if not viewer.get_realized():
                if self.stack.get_visible_child_name() != "3d_page":
                    self.stack.set_visible_child_name("3d_page")
                attempts = int(holder.get("_realize_attempts", 0)) + 1
                holder["_realize_attempts"] = attempts
                # ~2s at 16ms; mirrors split-compare abort so spinner cannot stick.
                if attempts > 120:
                    holder["cancelled"] = True
                    self.logger.warning(
                        "warm load: viewer never realized for %s",
                        kwargs.get("filepath"),
                    )
                    self._release_warm_holder_temps(holder)
                    if tab._warm_load_holder is holder:
                        tab._warm_load_holder = None
                    self.on_file_not_opened(kwargs.get("filepath"), tab)
                    self._unblock_reload_if_idle()
                    return GLib.SOURCE_REMOVE
                return GLib.SOURCE_CONTINUE
            if viewer.engine is None:
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
            self._unblock_reload_if_idle()
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
        load_ok = False

        if (not skip_auto_best
                and self.window_settings.get_setting("auto-best").value
                and not override and not add_file):
            self.logger.debug("choosing best settings")
            settings = "general"
            for key, value in self.configurations.items():
                if formats_pattern_matches(value.get("formats", ""), filepath):
                    settings = key
                    break
            self.logger.debug(f"best settings is {settings}")
            self.change_setting_state(GLib.Variant("s", settings))

        try:
            if holder.get("cancelled"):
                self._release_warm_holder_temps(holder)
                self._unblock_reload_if_idle()
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
            # load_file → engine.reset() wipes lights; restore shared view opts.
            try:
                viewer.update_options(
                    self.window_settings.get_view_settings(),
                    queue_render=True,
                )
            except Exception as exc:
                self.logger.debug("post-load view options: %s", exc)
            load_ok = True
        except Exception as exc:
            self.logger.error(f"Error while loading into viewer: {exc}")
            holder["_temps_released"] = True
            if load_path != filepath:
                release_prepared(load_path)
            self.on_file_not_opened(filepath, tab)
            return GLib.SOURCE_REMOVE
        finally:
            cleanup_decompressed(meshopt_temp)
            # Fail/cancel left the watcher stopped; resume for remaining docs.
            # Success path: on_file_opened calls run() — skip duplicate here.
            if not load_ok and any(
                getattr(t, "loaded", False) for t in self._iter_tabs()
            ):
                try:
                    self.change_checker.run()
                except Exception as exc:
                    self.logger.debug("change_checker restart failed: %s", exc)

        if preserve_orientation and camera_state is not None:
            try:
                viewer.set_camera_state(camera_state)
                # on_file_opened schedules done() — do not clobber restored cam.
                viewer._fit_camera_on_done = False
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
        # Coalesce list rebuild across batch opens.
        if getattr(self, "_recent_ui_idle", 0):
            return
        self._recent_ui_idle = GLib.idle_add(self._refresh_recent_files_ui_idle)

    def _refresh_recent_files_ui_idle(self) -> bool:
        self._recent_ui_idle = 0
        self._refresh_recent_files_ui()
        return GLib.SOURCE_REMOVE

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
        recent_list = getattr(self, "recent_files_list", None)
        recent_box = getattr(self, "recent_files_box", None)
        if recent_list is None:
            # Upstream startup UI has no recent list yet — still prune GSettings.
            stored = list(self.saved_settings.get_strv("recent-files"))
            paths = existing_recent(stored)
            if paths != stored:
                self.saved_settings.set_strv("recent-files", paths)
            return

        while True:
            child = recent_list.get_first_child()
            if child is None:
                break
            recent_list.remove(child)

        stored = list(self.saved_settings.get_strv("recent-files"))
        paths = existing_recent(stored)
        if paths != stored:
            # Drop missing paths so GSettings stays tidy.
            self.saved_settings.set_strv("recent-files", paths)
        if recent_box is not None:
            recent_box.set_visible(bool(paths))
        for path in paths:
            row = Adw.ActionRow(
                title=os.path.basename(path),
                subtitle=path,
                activatable=True,
            )
            row.connect("activated", self._on_recent_file_activated, path)
            recent_list.append(row)

    def _on_recent_file_activated(self, _row, path: str) -> None:
        if not os.path.isfile(path):
            self._refresh_recent_files_ui()
            self.on_file_not_opened(os.path.basename(path) or _("Unknown"))
            return
        # Route through the open queue so Recent never races an in-flight warm-load.
        self._open_model_paths([path])

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
        # This tab's open consumed disk state; keep peak only on sibling tabs.
        tab._blocked_peak_mtime = None
        tab.externally_modified = False
        if page is not None:
            self._configure_tab_page(page, tab)

        # Reveal the ready tab, or restore the page we left for GL realize.
        auto_select = getattr(tab, "_auto_select_on_open", True)
        restore = getattr(tab, "_restore_selected_page", None)
        tab._restore_selected_page = None
        if restore is not None and not auto_select:
            try:
                # Keep user on the tab they were viewing during batch opens.
                if self.tab_view.get_page_position(restore) >= 0:
                    self._switching_tab = True
                    self.tab_view.set_selected_page(restore)
                    self._switching_tab = False
            except Exception as exc:
                self.logger.debug("restore selected page after warm load: %s", exc)
        elif (
            auto_select
            and page is not None
            and self.tab_view.get_selected_page() != page
        ):
            self._switching_tab = True
            self.tab_view.set_selected_page(page)
            self._switching_tab = False
        if page is not None and self.tab_view.get_selected_page() == page:
            self._bind_animation_controls(tab.viewer)

        self.no_file_loaded = False
        # Reveal tab bar only once the 2nd+ model is ready.
        chrome_changed = self._update_tab_bar_visibility()

        self.update_time_stamp(tab)
        self.change_checker.run()

        # Title/focus only when this tab is (still) the selected one.
        if page is not None and self.tab_view.get_selected_page() == page:
            self.set_title(_("Exhibit - {}").format(self.file_name))
            self.title_widget.set_subtitle(self.file_name)
            self.stack.set_visible_child_name("3d_page")
            tab.viewer.grab_focus()

        self.update_background_color()
        self._remember_recent_file(tab.filepath)
        self._persist_session_files()
        # Advance may start the next warm-load (sets block_reload again).
        started_next = self._advance_open_queue()
        if not started_next:
            self._unblock_reload_if_idle()
        # Paint model first; sidebar extras can wait one idle tick.
        GLib.idle_add(self._post_open_sidebar_refresh)

        # Fit sooner when chrome already stable (3rd+ tab).
        GLib.timeout_add(120 if chrome_changed else 30, tab.viewer.done)
        return GLib.SOURCE_REMOVE

    def _post_open_sidebar_refresh(self):
        # Only refresh chrome bound to the active tab — background batch opens
        # must not stomp the sidebar with a sibling document's stats/combo.
        active = self._active_tab()
        if active is None or not getattr(active, "loaded", False):
            return GLib.SOURCE_REMOVE
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
            startup = getattr(self, "startup_stack", None)
            if startup is not None:
                try:
                    startup.set_visible_child_name("error_page")
                except Exception:
                    pass
            try:
                page = getattr(self, "error_status_page", None)
                if page is not None:
                    page.set_description(message)
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
        # Do not wipe window stats while sibling tabs still show a model.
        if self.no_file_loaded or not any(
            getattr(t, "loaded", False) for t in self._iter_tabs()
        ):
            self._mesh_stats = None
        elif hasattr(self, "_refresh_mesh_stats"):
            self._refresh_mesh_stats()
        self._update_tab_bar_visibility()

        started_next = self._advance_open_queue()
        if not started_next:
            self._unblock_reload_if_idle()
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
        switch = getattr(self, "use_skybox_switch", None)
        if switch is not None:
            switch.set_active(True)
        row = getattr(self, "hdri_file_row", None)
        if row is not None:
            try:
                row.set_filename(filepath)
            except Exception as exc:
                self.logger.debug("hdri_file_row: %s", exc)
        self._update_all_viewers_options(
            {"hdri-file": filepath, "hdri-skybox": True}
        )
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

