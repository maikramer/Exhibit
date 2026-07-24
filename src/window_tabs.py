# window_tabs.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tab / multi-document helpers extracted from Viewer3dWindow."""

from __future__ import annotations

import os

from gettext import gettext as _
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .camera_sync import apply_camera_state_to_peers, iter_camera_sync_peers
from .meshopt_decompress import cleanup_decompressed, release_prepared
from .warm_load import cancel_warm_load_holder, release_warm_holder_temps
from .widgets import F3DViewer, ViewerTab


class TabsMixin:
    @property
    def f3d_viewer(self):
        tab = self._active_tab()
        if tab is None:
            raise RuntimeError("No viewer tab available")
        return tab.viewer

    @property
    def stats_overlay_label(self):
        tab = self._active_tab()
        if tab is None:
            raise RuntimeError("No viewer tab available")
        return tab.stats_overlay_label

    def _active_tab(self) -> ViewerTab | None:
        page = self.tab_view.get_selected_page()
        if page is None:
            return None
        child = page.get_child()
        return child if isinstance(child, ViewerTab) else None

    def _tab_page(self, tab: ViewerTab):
        return self.tab_view.get_page(tab)

    def _iter_tabs(self):
        for i in range(self.tab_view.get_n_pages()):
            child = self.tab_view.get_nth_page(i).get_child()
            if isinstance(child, ViewerTab):
                yield child

    def _update_all_viewers_options(self, options, queue_render=True):
        for tab in self._iter_tabs():
            tab.viewer.update_options(options, queue_render=queue_render)
        split = getattr(self, "_split_compare_viewer", None)
        if split is not None:
            try:
                split.update_options(options, queue_render=queue_render)
            except Exception as exc:
                self.logger.debug(
                    "split compare options update failed: %s", exc
                )

    def _update_tab_bar_visibility(self) -> bool:
        # Only after 2+ models are ready — during 2nd open: no bar, full-bleed
        # loading cover on the new tab (feels like a single-file transition).
        loaded = sum(1 for t in self._iter_tabs() if t.loaded)
        want_bar = loaded > 1
        was_bar = self.tab_bar.get_visible()
        self.tab_bar.set_visible(want_bar)
        self.toolbar_view.set_extend_content_to_top_edge(not want_bar)
        chrome_changed = was_bar != want_bar
        if chrome_changed:
            GLib.timeout_add(100, self._reframe_after_chrome_change)
        return chrome_changed

    def _reframe_after_chrome_change(self):
        """Re-fit cameras after tab bar steals/returns vertical space."""
        for tab in self._iter_tabs():
            if not tab.loaded:
                continue
            viewer = tab.viewer
            if viewer.camera is None:
                continue
            try:
                viewer.reset_to_bounds()
            except Exception as exc:
                self.logger.debug(f"reframe skipped: {exc}")
        return GLib.SOURCE_REMOVE

    def _configure_tab_page(self, page, tab: ViewerTab):
        title = tab.tab_title(_("modified"), _("Untitled"))
        page.set_title(title)
        page.set_icon(Gio.ThemedIcon.new("image-x-generic-symbolic"))
        tooltip = tab.filepath or tab.file_name or title
        if tab.externally_modified and tab.filepath:
            tooltip = _("{path} — changed on disk").format(path=tab.filepath)
        if hasattr(page, "set_tooltip"):
            page.set_tooltip(tooltip)
        else:
            tab.set_tooltip_text(tooltip)

    def _refresh_tab_title(self, tab: ViewerTab | None):
        if tab is None:
            return
        page = self._tab_page(tab)
        if page is not None:
            self._configure_tab_page(page, tab)

    @staticmethod
    def _file_mtime(path: str) -> float | None:
        if not path:
            return None
        try:
            return os.stat(path).st_mtime
        except OSError:
            return None

    def _mark_tab_externally_modified(self, tab: ViewerTab, disk_mtime: float):
        tab.externally_modified = True
        tab.seen_disk_mtime = disk_mtime
        self._refresh_tab_title(tab)
        if tab is self._active_tab():
            self._sync_window_from_tab(tab)
        self.logger.info(
            f"External change: {tab.file_name or tab.filepath}")

    def _clear_tab_modified(self, tab: ViewerTab, disk_mtime: float | None = None):
        tab.externally_modified = False
        if disk_mtime is not None:
            tab.loaded_mtime = disk_mtime
            tab.seen_disk_mtime = disk_mtime
        self._refresh_tab_title(tab)
        if tab is self._active_tab():
            self._sync_window_from_tab(tab)

    def _prompt_reload_if_modified(self, tab: ViewerTab | None):
        if tab is None or not tab.externally_modified or not tab.filepath:
            return
        if tab._reload_dialog_open or self.block_reload:
            return
        if self.stack.get_visible_child_name() != "3d_page":
            return

        tab._reload_dialog_open = True
        name = tab.file_name or os.path.basename(tab.filepath)

        dialog = Adw.AlertDialog(
            heading=_("File changed on disk"),
            body=_("“{name}” was modified outside Exhibit. Reload the new version?").format(
                name=name
            ),
        )
        dialog.add_response("keep", _("Keep current"))
        dialog.add_response("reload", _("Reload"))
        dialog.set_response_appearance("reload", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("reload")
        dialog.set_close_response("keep")

        def on_response(_dialog, response):
            tab._reload_dialog_open = False
            if response == "reload":
                self._reload_tab(tab, preserve_orientation=True)
            else:
                # Acknowledge disk version so we don't re-prompt until next change.
                mtime = self._file_mtime(tab.filepath)
                if mtime is not None:
                    self._clear_tab_modified(tab, mtime)
                else:
                    self._clear_tab_modified(tab, tab.loaded_mtime)

        dialog.connect("response", on_response)
        dialog.present(self)
        return GLib.SOURCE_REMOVE


    def _reload_tab(self, tab: ViewerTab, preserve_orientation: bool = True):
        if not tab.filepath:
            return
        if self.block_reload:
            return
        if self._active_tab() is not tab:
            page = self._tab_page(tab)
            if page is not None:
                self._switching_tab = True
                self.tab_view.set_selected_page(page)
                self._switching_tab = False
                self._bind_animation_controls(tab.viewer)
                self._sync_window_from_tab(tab)
        self.load_file(
            filepath=tab.filepath,
            override=True,
            preserve_orientation=preserve_orientation,
            new_tab=False,
            _tab=tab,
        )

    def on_window_is_active(self, *args):
        if not self.get_property("is-active"):
            return
        self._prompt_reload_if_modified(self._active_tab())

    def _add_viewer_tab(self, title: str = "", select: bool = True) -> ViewerTab:
        tab = ViewerTab()
        if title:
            tab.file_name = title
        page = self.tab_view.append(tab)
        self._configure_tab_page(page, tab)
        tab.viewer.update_options(self.window_settings.get_view_settings())
        tab.viewer.camera_changed_cb = self._on_viewer_camera_changed
        apply_nav = getattr(self, "_apply_nav_settings_to_viewers", None)
        if callable(apply_nav) and hasattr(tab.viewer, "apply_nav_settings"):
            tab.viewer.apply_nav_settings(
                getattr(self, "_nav_settings_dict", lambda: {})()
            )
        if select:
            self.tab_view.set_selected_page(page)
            self._bind_animation_controls(tab.viewer)
        self._update_tab_bar_visibility()
        return tab

    def _on_sync_cameras_change(self, action, state):
        action.set_state(state)
        self._camera_sync = bool(state.get_boolean())
        if self._camera_sync:
            self._sync_peer_cameras_from_active()
            send = getattr(self, "send_toast", None)
            if callable(send):
                send(_("Camera sync on"), timeout=2)
        else:
            send = getattr(self, "send_toast", None)
            if callable(send):
                send(_("Camera sync off"), timeout=2)

    def _on_split_compare_change(self, action, state):
        """Toggle split-compare UI and lazily create a second F3D viewer."""
        action.set_state(state)
        enabled = bool(state.get_boolean())
        self._split_compare = enabled
        settings = getattr(self, "saved_settings", None)
        if settings is not None:
            try:
                settings.set_boolean("split-compare-enabled", enabled)
            except Exception:
                pass
        revealer = getattr(self, "split_compare_revealer", None)
        if revealer is not None:
            revealer.set_reveal_child(enabled)
        send = getattr(self, "send_toast", None)
        silent = bool(getattr(self, "_split_compare_restoring", False))
        if enabled:
            self._ensure_split_compare_viewer()
            self._size_split_compare_paned()
            GLib.idle_add(self._size_split_compare_paned)
            GLib.idle_add(self._load_split_compare_from_active)
            if callable(send) and not silent:
                send(_("Split compare on"), timeout=2)
        else:
            self._teardown_split_compare_viewer()
            self._split_compare_pinned = False
            self._split_compare_pin_filepath = None
            self._split_compare_pin_prepared = None
            pin = getattr(self, "split_compare_pin_check", None)
            if pin is not None and pin.get_active():
                pin.set_active(False)
            self._size_split_compare_paned()
            if callable(send) and not silent:
                send(_("Split compare off"), timeout=2)
        self._update_split_compare_swap_enabled()

    def _maybe_restore_split_compare(self) -> bool:
        """Re-enable Split Compare after startup when the flag is set (retry)."""
        settings = getattr(self, "saved_settings", None)
        if settings is None:
            return False
        try:
            want = bool(settings.get_boolean("split-compare-enabled"))
        except Exception:
            return False
        if not want or getattr(self, "_split_compare", False):
            return False
        attempts = int(getattr(self, "_split_restore_attempts", 0))
        if attempts > 40:
            return False
        self._split_restore_attempts = attempts + 1
        if not any(t.loaded for t in self._iter_tabs()):
            return True
        action = self.lookup_action("split-compare")
        if action is None:
            return False
        self._split_compare_restoring = True
        try:
            action.change_state(GLib.Variant("b", True))
        finally:
            self._split_compare_restoring = False
        GLib.idle_add(self._restore_split_compare_pin)
        return False

    def _clear_split_compare_pin_settings(self) -> None:
        settings = getattr(self, "saved_settings", None)
        if settings is None:
            return
        try:
            settings.set_boolean("split-compare-pinned", False)
            settings.set_string("split-compare-pin-path", "")
        except Exception:
            pass

    def _persist_split_compare_pin_settings(self, pinned: bool, filepath: str) -> None:
        settings = getattr(self, "saved_settings", None)
        if settings is None:
            return
        try:
            settings.set_boolean("split-compare-pinned", pinned)
            settings.set_string(
                "split-compare-pin-path", filepath if pinned and filepath else ""
            )
        except Exception:
            pass

    def _restore_split_compare_pin(self) -> bool:
        """Re-apply pinned secondary path if the file still exists."""
        settings = getattr(self, "saved_settings", None)
        if settings is None or not getattr(self, "_split_compare", False):
            return False
        try:
            want = bool(settings.get_boolean("split-compare-pinned"))
            path = (settings.get_string("split-compare-pin-path") or "").strip()
        except Exception:
            return False
        if not want or not path:
            return False
        if not os.path.isfile(path):
            self.logger.info(
                "split compare pin path missing, clearing: %s", path
            )
            self._clear_split_compare_pin_settings()
            return False
        self._split_compare_pin_filepath = path
        self._split_compare_pin_prepared = path
        self._split_compare_pinned = True
        pin = getattr(self, "split_compare_pin_check", None)
        if pin is None:
            GLib.idle_add(self._load_split_compare_from_active)
            return False
        self._split_compare_restoring = True
        try:
            if not pin.get_active():
                pin.set_active(True)
            else:
                GLib.idle_add(self._load_split_compare_from_active)
        finally:
            self._split_compare_restoring = False
        self._update_split_compare_swap_enabled()
        return False

    def _update_split_compare_swap_enabled(self) -> None:
        action = getattr(self, "split_compare_swap_action", None)
        button = getattr(self, "split_compare_swap_button", None)
        pin_path = getattr(self, "_split_compare_pin_filepath", None) or ""
        active = self._active_tab()
        active_path = (
            active.filepath
            if active is not None and getattr(active, "filepath", None)
            else ""
        )
        split_on = bool(getattr(self, "_split_compare", False))
        pinned = bool(getattr(self, "_split_compare_pinned", False))
        same = bool(
            pin_path
            and active_path
            and os.path.normpath(pin_path) == os.path.normpath(active_path)
        )
        pin_missing = bool(pin_path) and not os.path.isfile(pin_path)
        distinct = bool(
            pin_path and active_path and not same and not pin_missing
        )
        enabled = split_on and pinned and distinct
        if action is not None:
            action.set_enabled(enabled)

        if button is None:
            return
        if enabled:
            tip = _("Swap active and pinned models")
        elif not split_on:
            tip = _("Turn on Split Compare first")
        elif not pinned:
            tip = _("Pin another model, then swap with the active tab")
        elif pin_missing:
            tip = _("Pinned file is missing")
        elif same:
            tip = _("Pin another file to enable swap")
        elif not active_path:
            tip = _("Open a model in the active tab first")
        else:
            tip = _("Swap active and pinned models")
        button.set_tooltip_text(tip)

    def _on_split_compare_swap(self, *_args) -> None:
        """Swap the active tab model with the pinned secondary model."""
        send = getattr(self, "send_toast", None)

        def _toast(msg: str) -> None:
            if callable(send):
                send(msg, timeout=2)

        if not getattr(self, "_split_compare", False):
            _toast(_("Turn on Split Compare first"))
            return
        if not getattr(self, "_split_compare_pinned", False):
            _toast(_("Pin a secondary model first"))
            return
        pin_path = getattr(self, "_split_compare_pin_filepath", None)
        active = self._active_tab()
        if not pin_path or active is None or not active.filepath:
            _toast(_("Nothing to swap"))
            return
        if os.path.normpath(pin_path) == os.path.normpath(active.filepath):
            _toast(_("Active and pinned are the same file"))
            return
        if not os.path.isfile(pin_path):
            _toast(_("Pinned file is missing"))
            self._clear_split_compare_pin_settings()
            return

        prev_active = active.filepath
        prev_prepared = active.viewer.get_prepared_path() or prev_active
        pin_norm = os.path.normpath(pin_path)

        self._split_compare_pin_filepath = prev_active
        self._split_compare_pin_prepared = prev_prepared
        self._persist_split_compare_pin_settings(True, prev_active)

        target_tab = None
        for tab in self._iter_tabs():
            if tab.filepath and os.path.normpath(tab.filepath) == pin_norm:
                target_tab = tab
                break

        if target_tab is not None:
            page = self._tab_page(target_tab)
            if page is not None:
                self.tab_view.set_selected_page(page)
            else:
                GLib.idle_add(self._load_split_compare_from_active)
        else:
            self.load_file(
                filepath=pin_path, _tab=active, override=True
            )
            GLib.idle_add(self._load_split_compare_from_active)

        self._update_split_compare_swap_enabled()
        _toast(_("Swapped active and pinned"))

    def _on_split_compare_pin_toggled(self, check, *_args) -> None:
        pinned = bool(check.get_active())
        self._split_compare_pinned = pinned
        # Split off resets the checkbox only — keep GSettings for next reopen.
        if not getattr(self, "_split_compare", False):
            if not pinned:
                self._split_compare_pin_filepath = None
                self._split_compare_pin_prepared = None
            self._update_split_compare_swap_enabled()
            return
        silent = bool(getattr(self, "_split_compare_restoring", False))
        if pinned:
            if not (
                silent and getattr(self, "_split_compare_pin_filepath", None)
            ):
                active = self._active_tab()
                if active is not None and active.loaded and active.filepath:
                    self._split_compare_pin_filepath = active.filepath
                    self._split_compare_pin_prepared = (
                        active.viewer.get_prepared_path() or active.filepath
                    )
            filepath = getattr(self, "_split_compare_pin_filepath", None) or ""
            if not silent:
                self._persist_split_compare_pin_settings(True, filepath)
            GLib.idle_add(self._load_split_compare_from_active)
            send = getattr(self, "send_toast", None)
            if callable(send) and not silent:
                send(_("Secondary model pinned"), timeout=2)
        else:
            self._split_compare_pin_filepath = None
            self._split_compare_pin_prepared = None
            if not silent:
                self._clear_split_compare_pin_settings()
            GLib.idle_add(self._load_split_compare_from_active)
        self._update_split_compare_swap_enabled()

    def _size_split_compare_paned(self) -> None:
        """Place the main horizontal split from saved ratio when compare is on."""
        main = getattr(self, "split_compare_main_paned", None)
        inner = getattr(self, "split_compare_paned", None)
        if inner is not None:
            inner.set_vexpand(True)
            inner.set_position(0)
        if main is None:
            return
        enabled = bool(getattr(self, "_split_compare", False))
        try:
            main.set_wide_handle(enabled)
        except Exception:
            pass
        try:
            total = max(int(main.get_width()), int(self.get_width()), 800)
        except Exception:
            total = 1000
        self._split_compare_sizing = True
        try:
            if not enabled:
                main.set_position(total)
                return
            ratio = 0.62
            settings = getattr(self, "saved_settings", None)
            if settings is not None:
                try:
                    ratio = float(settings.get_double("split-compare-sash-ratio"))
                except Exception:
                    ratio = 0.62
            ratio = min(0.80, max(0.45, ratio))
            main.set_position(int(total * ratio))
        finally:
            self._split_compare_sizing = False

    def _on_split_compare_sash_changed(self, paned, *_args) -> None:
        if getattr(self, "_split_compare_sizing", False):
            return
        if not getattr(self, "_split_compare", False):
            return
        # Keep GL surfaces fresh while the user drags the sash.
        try:
            tab = self._active_tab()
            if tab is not None and getattr(tab, "viewer", None) is not None:
                tab.viewer.queue_render()
        except Exception:
            pass
        split = getattr(self, "_split_compare_viewer", None)
        if split is not None:
            try:
                split.queue_render()
            except Exception:
                pass
        save_id = getattr(self, "_split_compare_sash_save_id", 0)
        if save_id:
            try:
                GLib.source_remove(save_id)
            except Exception:
                pass
        self._split_compare_sash_save_id = GLib.timeout_add(
            300, self._persist_split_compare_sash_ratio
        )

    def _persist_split_compare_sash_ratio(self) -> bool:
        self._split_compare_sash_save_id = 0
        if not getattr(self, "_split_compare", False):
            return False
        main = getattr(self, "split_compare_main_paned", None)
        settings = getattr(self, "saved_settings", None)
        if main is None or settings is None:
            return False
        try:
            total = max(int(main.get_width()), 1)
            pos = int(main.get_position())
            ratio = min(0.80, max(0.45, pos / total))
            settings.set_double("split-compare-sash-ratio", ratio)
        except Exception as exc:
            self.logger.debug("split compare sash persist failed: %s", exc)
        return False

    def _ensure_split_compare_viewer(self) -> None:
        if getattr(self, "_split_compare_viewer", None) is not None:
            return
        paned = getattr(self, "split_compare_paned", None)
        if paned is None:
            return
        stub = paned.get_end_child()
        if stub is not None and not isinstance(stub, F3DViewer):
            self._split_compare_stub = stub
        viewer = F3DViewer()
        viewer.add_css_class("f3d-render")
        viewer.set_hexpand(True)
        viewer.set_vexpand(True)
        try:
            viewer.update_options(self.window_settings.get_view_settings())
        except Exception as exc:
            self.logger.debug("split compare options failed: %s", exc)
        paned.set_end_child(viewer)
        self._split_compare_viewer = viewer
        self._size_split_compare_paned()

    def _teardown_split_compare_viewer(self) -> None:
        viewer = getattr(self, "_split_compare_viewer", None)
        paned = getattr(self, "split_compare_paned", None)
        self._split_compare_viewer = None
        if viewer is not None:
            try:
                viewer.release_resources()
            except Exception as exc:
                self.logger.warning(
                    "split compare: release_resources failed: %s", exc
                )
        if paned is None:
            return
        stub = getattr(self, "_split_compare_stub", None)
        if stub is not None:
            paned.set_end_child(stub)
        else:
            label = Gtk.Label(label=_("Secondary (stub)"))
            paned.set_end_child(label)
            self._split_compare_stub = label

    def _load_split_compare_from_active(self) -> bool:
        """Load into secondary viewer (idle-safe); respect pin when set."""
        viewer = getattr(self, "_split_compare_viewer", None)
        if viewer is None or not getattr(self, "_split_compare", False):
            return False

        pinned = getattr(self, "_split_compare_pinned", False)
        active = self._active_tab()
        if pinned and getattr(self, "_split_compare_pin_filepath", None):
            filepath = self._split_compare_pin_filepath
            prepared = self._split_compare_pin_prepared or filepath
        else:
            if active is None or not active.loaded or not active.filepath:
                return False
            filepath = active.filepath
            prepared = active.viewer.get_prepared_path() or active.filepath

        label = getattr(self, "split_compare_primary_label", None)
        if label is not None:
            name = os.path.basename(filepath)
            active_name = ""
            if active is not None and active.filepath:
                active_name = os.path.basename(active.filepath)
            if pinned:
                if active_name and active_name != name:
                    label.set_label(
                        _("Pinned: {}\nActive: {}").format(name, active_name)
                    )
                else:
                    label.set_label(_("Pinned: {}").format(name))
            else:
                label.set_label(_("Following: {}").format(name))

        try:
            already = getattr(viewer, "_loaded_filepath", None)
            need_load = already not in (filepath, prepared)
            if need_load:
                viewer.update_options(self.window_settings.get_view_settings())
                viewer.load_file(filepath, prepared_path=prepared)
            # Camera always follows the active tab when available.
            if active is not None and active.loaded:
                state = active.viewer.get_camera_state()
                if state is not None:
                    viewer.set_camera_state(state)
        except Exception as exc:
            self.logger.warning("split compare load failed: %s", exc)
            send = getattr(self, "send_toast", None)
            if callable(send):
                send(_("Couldn't load split compare view"), timeout=3)
        return False

    def _sync_peer_cameras_from_active(self) -> None:
        active = self._active_tab()
        if active is None or not active.loaded:
            return
        try:
            state = active.viewer.get_camera_state()
        except Exception as exc:
            self.logger.debug("camera sync: get state failed: %s", exc)
            return
        if state is None:
            return
        self._apply_camera_state_to_peers(active.viewer, state)

    def _on_viewer_camera_changed(self, viewer) -> None:
        if not getattr(self, "_camera_sync", False) and not getattr(
            self, "_split_compare", False
        ):
            return
        if getattr(self, "_syncing_cameras", False):
            return
        active = self._active_tab()
        if active is None or active.viewer is not viewer:
            return
        try:
            state = viewer.get_camera_state()
        except Exception as exc:
            self.logger.debug("camera sync: get state failed: %s", exc)
            return
        if state is None:
            return
        self._apply_camera_state_to_peers(viewer, state)

    def _apply_camera_state_to_peers(self, source_viewer, state) -> None:
        self._syncing_cameras = True
        try:
            tabs = (
                self._iter_tabs()
                if getattr(self, "_camera_sync", False)
                else []
            )
            extras = None
            if getattr(self, "_split_compare", False):
                extras = [getattr(self, "_split_compare_viewer", None)]
            peers = iter_camera_sync_peers(
                tabs, source=source_viewer, extras=extras
            )
            apply_camera_state_to_peers(
                peers,
                state,
                on_error=lambda _viewer, exc: self.logger.debug(
                    "camera sync to peer failed: %s", exc
                ),
            )
        finally:
            self._syncing_cameras = False

    def _sync_window_from_tab(self, tab: ViewerTab | None):
        if tab is None:
            self.filepath = ""
            self.file_name = ""
            self._mesh_stats = None
            return
        self.filepath = tab.filepath
        self.file_name = tab.file_name
        self._mesh_stats = tab.mesh_stats
        # Keep per-tab x-ray / depth restore; do not invent defaults across switches.
        self._armature_xray_restore = tab.armature_xray_restore
        self._depth_opacity_restore = tab.depth_opacity_restore
        if tab.loaded:
            label = tab.tab_title(_("modified"), _("Untitled"))
            self.set_title(_("Exhibit - {}").format(label))
            self.title_widget.set_subtitle(label)
        else:
            self.set_title(_("Exhibit"))
            self.title_widget.set_subtitle(_("Asset preview"))

    def on_tab_selected_page(self, *args):
        if self._switching_tab:
            return
        tab = self._active_tab()
        if tab is None:
            return
        self._switching_tab = True
        try:
            self._bind_animation_controls(tab.viewer)
            self._sync_window_from_tab(tab)
            if tab.loaded:
                self.no_file_loaded = False
                self.refresh_animation_combo()
                self.refresh_object_tree()
                if self.window_settings.get_setting("stats-overlay").value:
                    self._apply_stats_overlay(True)
                else:
                    tab.stats_overlay_label.set_visible(False)
                # Do not baseline/clear (modified) here — that races the prompt.
                self.change_checker.run()
                tab.viewer.grab_focus()
                # Ensure GL picks up the visible allocation after a switch.
                GLib.idle_add(tab.viewer.queue_render)
                GLib.idle_add(self._prompt_reload_if_modified, tab)
                if getattr(self, "_split_compare", False):
                    GLib.idle_add(self._load_split_compare_from_active)
            self._update_tab_bar_visibility()
            self._update_split_compare_swap_enabled()
        finally:
            self._switching_tab = False

    def _release_warm_holder_temps(self, holder: dict) -> None:
        """Drop prepare temps owned by a cancelled/abandoned warm-load holder."""
        release_warm_holder_temps(
            holder,
            cleanup_temp=cleanup_decompressed,
            release_prepared=release_prepared,
        )

    def _cancel_warm_load(self, tab: ViewerTab) -> None:
        """Abort in-flight warm load for a tab and free retained prepare temps."""
        holder = getattr(tab, "_warm_load_holder", None)
        tab._warm_load_holder = None
        if cancel_warm_load_holder(holder) is None:
            return
        self._release_warm_holder_temps(holder)

    def on_tab_close_page(self, tab_view, page):
        tab = page.get_child()
        closing_viewer = tab.viewer if isinstance(tab, ViewerTab) else None
        was_selected = self.tab_view.get_selected_page() == page

        # Block notify::selected-page re-entrancy while pages reshuffle.
        self._switching_tab = True
        created_empty = False
        try:
            if was_selected:
                self._unbind_animation_controls(closing_viewer)

            self.tab_view.close_page_finish(page, True)
            if isinstance(tab, ViewerTab):
                self._cancel_warm_load(tab)
                # Drop window-owned skin-weight heat pointer (viewer unlinks file).
                if was_selected and getattr(self, "_skin_weights_heat_temp", None):
                    self._skin_weights_heat_temp = None
                    self._skin_weights_base_path = None
                try:
                    tab.viewer.release_resources()
                except Exception as exc:
                    self.logger.warning(
                        "tab close: release_resources failed: %s", exc
                    )
                tab.mesh_stats = None
                tab.loaded = False
                try:
                    tab.clear_overlays()
                except Exception as exc:
                    self.logger.debug("tab close: clear_overlays failed: %s", exc)

            if self.tab_view.get_n_pages() == 0:
                self.no_file_loaded = True
                self.filepath = ""
                self.file_name = ""
                self._mesh_stats = None
                self.change_checker.stop()
                self.set_title(_("Exhibit"))
                self.title_widget.set_subtitle(_("Asset preview"))
                self.stack.set_visible_child_name("startup_page")
                self.startup_stack.set_visible_child_name("welcome_page")
                self._add_viewer_tab(select=True)
                created_empty = True
        finally:
            self._switching_tab = False

        # Empty-tab path already bound via _add_viewer_tab(select=True).
        if was_selected and not created_empty and self.tab_view.get_n_pages() > 0:
            self.on_tab_selected_page()
        self._update_tab_bar_visibility()
        return Gdk.EVENT_STOP

