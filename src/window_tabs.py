# window_tabs.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tab / multi-document helpers extracted from Viewer3dWindow."""

from __future__ import annotations

import os

from gettext import gettext as _
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .camera_sync import apply_camera_state_to_peers, iter_camera_sync_peers
from .window_settings_ui import up_dir_n_to_string
from .meshopt_decompress import (
    cleanup_decompressed,
    release_prepared,
    retain_prepared,
)
from .warm_load import cancel_warm_load_holder, release_warm_holder_temps
from .widgets.f3d_viewer import F3DViewer
from .widgets.viewer_tab import ViewerTab


class TabsMixin:
    _CLOSED_TABS_MAX = 20

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

    def _setup_tab_context_menu(self) -> None:
        """Right-click tab menu: close variants + reopen closed."""
        self._closed_tabs: list[str] = []
        self._tab_menu_page = None

        close_section = Gio.Menu()
        close_section.append(_("Close Tab"), "win.tab-close")
        close_section.append(_("Close Other Tabs"), "win.tab-close-other")
        close_section.append(_("Close Tabs to the Left"), "win.tab-close-before")
        close_section.append(_("Close Tabs to the Right"), "win.tab-close-after")

        reopen_section = Gio.Menu()
        reopen_section.append(_("Reopen Closed Tab"), "win.tab-reopen-closed")

        menu = Gio.Menu()
        menu.append_section(None, close_section)
        menu.append_section(None, reopen_section)
        self.tab_view.set_menu_model(menu)

        self._tab_close_action = Gio.SimpleAction.new("tab-close", None)
        self._tab_close_action.connect("activate", self._on_tab_close_action)
        self.add_action(self._tab_close_action)

        self._tab_close_other_action = Gio.SimpleAction.new(
            "tab-close-other", None
        )
        self._tab_close_other_action.connect(
            "activate", self._on_tab_close_other_action
        )
        self.add_action(self._tab_close_other_action)

        self._tab_close_before_action = Gio.SimpleAction.new(
            "tab-close-before", None
        )
        self._tab_close_before_action.connect(
            "activate", self._on_tab_close_before_action
        )
        self.add_action(self._tab_close_before_action)

        self._tab_close_after_action = Gio.SimpleAction.new(
            "tab-close-after", None
        )
        self._tab_close_after_action.connect(
            "activate", self._on_tab_close_after_action
        )
        self.add_action(self._tab_close_after_action)

        self._tab_reopen_closed_action = Gio.SimpleAction.new(
            "tab-reopen-closed", None
        )
        self._tab_reopen_closed_action.connect(
            "activate", self._on_tab_reopen_closed_action
        )
        self._tab_reopen_closed_action.set_enabled(False)
        self.add_action(self._tab_reopen_closed_action)

        self.tab_view.connect("setup-menu", self._on_tab_setup_menu)

        # Ctrl+W is camera move-forward on the viewer — do not steal it.
        app = self.get_application()
        if app is not None:
            app.set_accels_for_action(
                "win.tab-reopen-closed", ["<Primary><Shift>t"]
            )

    def _tab_menu_target_page(self):
        return self._tab_menu_page or self.tab_view.get_selected_page()

    def _on_tab_setup_menu(self, _tab_view, page) -> None:
        self._tab_menu_page = page
        if page is None:
            self._update_tab_menu_actions(None)
            return
        self._update_tab_menu_actions(page)

    def _update_tab_menu_actions(self, page) -> None:
        n_pages = self.tab_view.get_n_pages()
        if page is None:
            selected = self.tab_view.get_selected_page()
            has_page = selected is not None
            index = (
                self.tab_view.get_page_position(selected) if has_page else -1
            )
        else:
            has_page = True
            index = self.tab_view.get_page_position(page)

        self._tab_close_action.set_enabled(has_page and n_pages > 0)
        self._tab_close_other_action.set_enabled(has_page and n_pages > 1)
        self._tab_close_before_action.set_enabled(has_page and index > 0)
        self._tab_close_after_action.set_enabled(
            has_page and 0 <= index < n_pages - 1
        )
        self._update_tab_reopen_action()

    def _update_tab_reopen_action(self) -> None:
        action = getattr(self, "_tab_reopen_closed_action", None)
        if action is None:
            return
        action.set_enabled(bool(self._closed_tabs))

    def _push_closed_tab(self, tab: ViewerTab) -> None:
        path = getattr(tab, "filepath", None) or ""
        if not path:
            return
        closed = getattr(self, "_closed_tabs", None)
        if closed is None:
            self._closed_tabs = []
            closed = self._closed_tabs
        closed.append(path)
        overflow = len(closed) - self._CLOSED_TABS_MAX
        if overflow > 0:
            del closed[:overflow]
        self._update_tab_reopen_action()

    def _on_tab_close_action(self, *_args) -> None:
        page = self._tab_menu_target_page()
        if page is not None:
            self.tab_view.close_page(page)

    def _on_tab_close_other_action(self, *_args) -> None:
        page = self._tab_menu_target_page()
        if page is not None:
            self.tab_view.close_other_pages(page)

    def _on_tab_close_before_action(self, *_args) -> None:
        page = self._tab_menu_target_page()
        if page is not None:
            self.tab_view.close_pages_before(page)

    def _on_tab_close_after_action(self, *_args) -> None:
        page = self._tab_menu_target_page()
        if page is not None:
            self.tab_view.close_pages_after(page)

    def _on_tab_reopen_closed_action(self, *_args) -> None:
        closed = getattr(self, "_closed_tabs", None)
        if not closed:
            self._update_tab_reopen_action()
            return
        while closed:
            path = closed.pop()
            if os.path.isfile(path):
                # Queue-safe: never race an in-flight warm-load.
                self._open_model_paths([path])
                break
        self._update_tab_reopen_action()

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

    @staticmethod
    def _norm_tab_path(filepath: str) -> str:
        if not filepath:
            return ""
        try:
            return os.path.realpath(filepath)
        except OSError:
            return os.path.normpath(filepath)

    def _find_tab_by_filepath(self, filepath: str) -> ViewerTab | None:
        target = self._norm_tab_path(filepath)
        if not target:
            return None
        for tab in self._iter_tabs():
            if not tab.filepath:
                continue
            if self._norm_tab_path(tab.filepath) == target:
                return tab
        return None

    def _flash_tab_attention(
        self, page, duration_ms: int = 2000, on_done=None
    ) -> None:
        """Pulse Adw.TabPage needs-attention for ``duration_ms``."""
        if page is None:
            return
        interval_ms = 200
        flashes = max(1, int(duration_ms / interval_ms))
        state = {"on": True, "left": flashes}
        page.set_needs_attention(True)

        tokens = getattr(self, "_tab_flash_tokens", None)
        if tokens is None:
            tokens = {}
            self._tab_flash_tokens = tokens
        token = object()
        tokens[id(page)] = token

        def tick():
            if tokens.get(id(page)) is not token:
                return GLib.SOURCE_REMOVE
            state["left"] -= 1
            if state["left"] <= 0:
                page.set_needs_attention(False)
                tokens.pop(id(page), None)
                if callable(on_done):
                    on_done()
                return GLib.SOURCE_REMOVE
            state["on"] = not state["on"]
            page.set_needs_attention(state["on"])
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(interval_ms, tick)

    def _focus_existing_tab(self, tab: ViewerTab) -> None:
        """Select an already-open tab and flash it for feedback."""
        page = self._tab_page(tab)
        if page is None:
            return
        if self.tab_view.get_selected_page() != page:
            self._switching_tab = True
            try:
                self.tab_view.set_selected_page(page)
            finally:
                self._switching_tab = False
            self.on_tab_selected_page()
        self._update_tab_bar_visibility()
        # Show bar for the flash even when a single tab would hide it.
        forced_bar = False
        if not self.tab_bar.get_visible():
            self.tab_bar.set_visible(True)
            self.toolbar_view.set_extend_content_to_top_edge(False)
            forced_bar = True

        def _after_flash():
            if forced_bar:
                self._update_tab_bar_visibility()

        self._flash_tab_attention(
            page, duration_ms=2000, on_done=_after_flash
        )
        name = tab.file_name or (
            os.path.basename(tab.filepath) if tab.filepath else _("Untitled")
        )
        send = getattr(self, "send_toast", None)
        if callable(send):
            send(_("Already open: {}").format(name), timeout=2)

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

    # Sidebar widgets bind to template Exb.Engine (seed / tab 0 only). Mirror
    # those property changes onto every other tab + split compare.
    _ENGINE_FANOUT_PROPS = (
        "light-intensity",
        "hdri-ambient",
        "hdri-skybox",
        "hdri-file",
        "blur-background",
        "blur-coc",
        "tone-mapping",
        "ambient-occlusion",
        "anti-aliasing",
        "blending",
        "volume-rendering",
        "volume-inverse-opacity",
        "bloom",
        "bloom-threshold",
        "bloom-intensity",
        "bloom-radius",
        "godrays",
        "godrays-intensity",
        "godrays-decay",
        "godrays-density",
        "godrays-weight",
        "ao-radius",
        "ao-bias",
        "ao-kernel-size",
        "ao-intensity",
        "show-edges",
        "edges-width",
        "point-size",
        "sprites",
        "sprites-size",
        "model-metallic",
        "model-roughness",
        "model-opacity",
        "model-color",
        "show-grid",
        "grid-absolute",
        "background-color",
        "up",
        "show-armature",
    )

    def _wire_engine_option_fanout(self) -> None:
        eng = getattr(self, "engine", None)
        if eng is None:
            return
        self._engine_fanout_block = False
        for prop in self._ENGINE_FANOUT_PROPS:
            try:
                eng.connect(
                    f"notify::{prop}", self._on_template_engine_option, prop
                )
            except Exception as exc:
                self.logger.debug("engine fanout connect %s: %s", prop, exc)

    def _copy_template_engine_to_viewer(self, viewer) -> None:
        """Push current sidebar-bound engine props onto a secondary viewer."""
        eng = getattr(self, "engine", None)
        peer = getattr(viewer, "engine", None)
        if eng is None or peer is None or peer is eng:
            return
        for prop in self._ENGINE_FANOUT_PROPS:
            try:
                peer.set_property(prop, eng.get_property(prop))
            except Exception:
                continue
        if hasattr(viewer, "queue_render"):
            viewer.queue_render()

    # Engine GObject props → WindowSettings keys (presets / save parity).
    _ENGINE_PROP_TO_SETTING = {
        "show-grid": "grid",
        "grid-absolute": "grid-absolute",
        "show-armature": "armature-enable",
        "background-color": "bg-color",
        "model-color": "model-color",
        "light-intensity": "light-intensity",
        "hdri-ambient": "hdri-ambient",
        "hdri-skybox": "hdri-skybox",
        "hdri-file": "hdri-file",
        "blur-background": "blur-background",
        "blur-coc": "blur-coc",
        "tone-mapping": "tone-mapping",
        "ambient-occlusion": "ambient-occlusion",
        "show-edges": "show-edges",
        "edges-width": "edges-width",
        "model-opacity": "model-opacity",
        "model-metallic": "model-metallic",
        "model-roughness": "model-roughness",
        "bloom": "bloom",
        "bloom-threshold": "bloom-threshold",
        "bloom-intensity": "bloom-intensity",
        "bloom-radius": "bloom-radius",
        "godrays": "godrays",
        "godrays-intensity": "godrays-intensity",
        "godrays-decay": "godrays-decay",
        "godrays-density": "godrays-density",
        "godrays-weight": "godrays-weight",
        "ao-radius": "ao-radius",
        "ao-bias": "ao-bias",
        "ao-kernel-size": "ao-kernel-size",
        "ao-intensity": "ao-intensity",
        "anti-aliasing": "anti-aliasing",
        "blending": "translucency-support",
        "volume-rendering": "volume",
        "volume-inverse-opacity": "inverse",
        "sprites": "sprites-type",
        "sprites-size": "sprites-size",
        "point-size": "point-size",
        "up": "up",
    }

    def _sync_engine_prop_to_window_settings(self, prop: str, value) -> None:
        """Keep WindowSettings aligned with sidebar-bound template engine."""
        key = self._ENGINE_PROP_TO_SETTING.get(prop)
        if key is None:
            return
        setting = self.window_settings.get_setting(key)
        if setting is None:
            return
        if prop in ("background-color", "model-color"):
            try:
                normalized = [value.red, value.green, value.blue]
            except Exception:
                return
        elif prop == "hdri-file":
            if value is None:
                normalized = ""
            elif hasattr(value, "get_path"):
                try:
                    normalized = value.get_path() or ""
                except Exception:
                    normalized = ""
            else:
                normalized = str(value)
        elif prop == "up":
            try:
                normalized = up_dir_n_to_string.get(int(value), "+Y")
            except Exception:
                return
        elif prop == "anti-aliasing":
            try:
                from gi.repository import Exb

                normalized = value != Exb.AntiAliasing.NONE
            except Exception:
                normalized = bool(value)
        elif prop == "blending":
            # Sidebar Exb.Blending → preset bool translucency-support.
            try:
                from gi.repository import Exb

                normalized = value != Exb.Blending.NONE
            except Exception:
                normalized = bool(value)
        elif prop == "sprites":
            try:
                from gi.repository import Exb

                if value == Exb.Sprites.NONE:
                    # Also clear sprite-enabled without stomping type unnecessarily.
                    en = self.window_settings.get_setting("sprite-enabled")
                    if en is not None and en.value:
                        self.window_settings.set_setting(
                            "sprite-enabled", False, False
                        )
                    return
                nick = getattr(value, "value_nick", None) or str(value)
                normalized = str(nick).replace("_", "-").lower()
                en = self.window_settings.get_setting("sprite-enabled")
                if en is not None and not en.value:
                    self.window_settings.set_setting(
                        "sprite-enabled", True, False
                    )
            except Exception:
                return
        else:
            normalized = value
        try:
            if setting.value == normalized:
                return
            # update=False: avoid reload storms; presets/save still see truth.
            self.window_settings.set_setting(key, normalized, False)
            check = getattr(self, "check_for_options_change", None)
            if callable(check):
                check()
        except Exception as exc:
            self.logger.debug("engine→settings %s: %s", prop, exc)

    def _on_template_engine_option(self, engine, _pspec, prop: str) -> None:
        if getattr(self, "_engine_fanout_block", False):
            return
        if getattr(self, "_switching_tab", False):
            return
        try:
            value = engine.get_property(prop)
        except Exception:
            return
        self._engine_fanout_block = True
        try:
            for tab in self._iter_tabs():
                viewer = getattr(tab, "viewer", None)
                peer = getattr(viewer, "engine", None) if viewer else None
                if peer is None or peer is engine:
                    continue
                try:
                    peer.set_property(prop, value)
                    if hasattr(viewer, "queue_render"):
                        viewer.queue_render()
                except Exception as exc:
                    self.logger.debug(
                        "engine fanout %s → tab: %s", prop, exc
                    )
            split = getattr(self, "_split_compare_viewer", None)
            if split is not None:
                peer = getattr(split, "engine", None)
                if peer is not None and peer is not engine:
                    try:
                        peer.set_property(prop, value)
                        split.queue_render()
                    except Exception as exc:
                        self.logger.debug(
                            "engine fanout %s → split: %s", prop, exc
                        )
            self._sync_engine_prop_to_window_settings(prop, value)
        finally:
            self._engine_fanout_block = False

    def _update_tab_bar_visibility(self) -> bool:
        # AdwTabBar.autohide shows the bar when n_pages > 1. Still toggle
        # extend-content so the floating header does not eat tab-bar space.
        want_bar = self.tab_view.get_n_pages() > 1
        was_extend = bool(self.toolbar_view.get_extend_content_to_top_edge())
        # Single-doc: full-bleed under header. Multi-doc: reserve top chrome.
        self.toolbar_view.set_extend_content_to_top_edge(not want_bar)
        # Force reveal even if autohide lags during the 2nd open.
        if want_bar:
            self.tab_bar.set_visible(True)
        self._sync_object_tree_overlay_margin(want_bar)
        chrome_changed = was_extend != (not want_bar)
        if chrome_changed:
            GLib.timeout_add(100, self._reframe_after_chrome_change)
        return chrome_changed

    def _sync_object_tree_overlay_margin(self, tab_bar_visible: bool) -> None:
        """Keep outliner chrome tight to header/tabs (no double top gap)."""
        shell = getattr(self, "object_tree_overlay_shell", None)
        if shell is None:
            return
        # Full-bleed under header needs clearance for sidebar/home.
        # With tabs, content already starts below the bar — small inset only.
        shell.set_margin_top(8 if tab_bar_visible else 56)

    def _reframe_after_chrome_change(self):
        """Re-fit visible cameras after tab bar steals/returns vertical space."""
        # Only active (+ split) — other tabs keep their camera until selected.
        targets = []
        active = self._active_tab()
        if active is not None and active.loaded:
            targets.append(active.viewer)
        if getattr(self, "_split_compare", False):
            split = getattr(self, "_split_compare_viewer", None)
            if split is not None:
                targets.append(split)
        for viewer in targets:
            if viewer is None or getattr(viewer, "camera", None) is None:
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

    def _add_viewer_tab(
        self,
        title: str = "",
        select: bool = True,
        viewer=None,
    ) -> ViewerTab:
        tab = ViewerTab(viewer=viewer)
        if title:
            tab.file_name = title
        page = self.tab_view.append(tab)
        self._configure_tab_page(page, tab)
        # New engines start empty — seed from shared WindowSettings (and copy
        # live template-engine values so sidebar binds stay in sync).
        if not getattr(tab.viewer, "_bridge", False):
            tab.viewer.update_options(self.window_settings.get_view_settings())
            self._copy_template_engine_to_viewer(tab.viewer)
        tab.viewer.camera_changed_cb = self._on_viewer_camera_changed
        if hasattr(tab.viewer, "apply_nav_settings"):
            tab.viewer.apply_nav_settings(
                getattr(self, "_nav_settings_dict", lambda: {})()
            )
        seed_point = getattr(self, "_apply_point_up_to_viewer", None)
        if callable(seed_point):
            seed_point(tab.viewer)
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
            except Exception as exc:
                self.logger.debug("split-compare-enabled persist failed: %s", exc)
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
        except Exception as exc:
            self.logger.debug("split-compare pin clear failed: %s", exc)

    def _persist_split_compare_pin_settings(self, pinned: bool, filepath: str) -> None:
        settings = getattr(self, "saved_settings", None)
        if settings is None:
            return
        try:
            settings.set_boolean("split-compare-pinned", pinned)
            settings.set_string(
                "split-compare-pin-path", filepath if pinned and filepath else ""
            )
        except Exception as exc:
            self.logger.debug("split-compare pin persist failed: %s", exc)

    def _restore_split_compare_pin(self) -> bool:
        """Re-apply pinned secondary path if the file still exists."""
        settings = getattr(self, "saved_settings", None)
        if settings is None or not getattr(self, "_split_compare", False):
            return False
        try:
            want = bool(settings.get_boolean("split-compare-pinned"))
            path = (settings.get_string("split-compare-pin-path") or "").strip()
        except Exception as exc:
            self.logger.debug("split compare pin restore read failed: %s", exc)
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
        # Temps do not survive restart — force prepare on next secondary load.
        self._split_compare_pin_prepared = None
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
        except Exception as exc:
            self.logger.debug("split compare wide_handle failed: %s", exc)
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
                except Exception as exc:
                    self.logger.debug("split-compare sash ratio read failed: %s", exc)
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
        except Exception as exc:
            self.logger.debug("split compare queue_render (main) failed: %s", exc)
        split = getattr(self, "_split_compare_viewer", None)
        if split is not None:
            try:
                split.queue_render()
            except Exception as exc:
                self.logger.debug("split compare queue_render (split) failed: %s", exc)
        save_id = getattr(self, "_split_compare_sash_save_id", 0)
        if save_id:
            try:
                GLib.source_remove(save_id)
            except Exception as exc:
                self.logger.debug("split compare sash timer remove failed: %s", exc)
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
        """Lazily create secondary F3DViewer in template split_compare_paned."""
        if getattr(self, "_split_compare_viewer", None) is not None:
            return
        paned = getattr(self, "split_compare_paned", None)
        if paned is None:
            self.logger.warning("split compare: paned missing from window.ui")
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
            self._copy_template_engine_to_viewer(viewer)
        except Exception as exc:
            self.logger.debug("split compare options failed: %s", exc)
        if hasattr(viewer, "apply_nav_settings"):
            try:
                viewer.apply_nav_settings(
                    getattr(self, "_nav_settings_dict", lambda: {})()
                )
            except Exception as exc:
                self.logger.debug("split compare nav seed failed: %s", exc)
        seed_point = getattr(self, "_apply_point_up_to_viewer", None)
        if callable(seed_point):
            try:
                seed_point(viewer)
            except Exception as exc:
                self.logger.debug("split compare point-up seed failed: %s", exc)
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
            prepared = getattr(self, "_split_compare_pin_prepared", None)
        else:
            if active is None or not active.loaded or not active.filepath:
                return False
            filepath = active.filepath
            prepared = active.viewer.get_prepared_path()
        # Only reuse a distinct prepared temp that still exists; else prepare.
        if (
            not prepared
            or prepared == filepath
            or not os.path.isfile(prepared)
        ):
            prepared = None

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

        retained = False
        try:
            # Secondary GLArea must realize before load_file (Exb defers if
            # scene is still NULL — same race as primary warm-load).
            if not viewer.get_realized():
                attempts = int(
                    getattr(self, "_split_load_realize_attempts", 0)
                )
                if attempts < 120:
                    self._split_load_realize_attempts = attempts + 1
                    GLib.timeout_add(16, self._load_split_compare_from_active)
                else:
                    self._split_load_realize_attempts = 0
                    self.logger.warning(
                        "split compare: secondary viewer never realized"
                    )
                return False
            if viewer.engine is None:
                viewer.initialize()
            self._split_load_realize_attempts = 0

            already = getattr(viewer, "_loaded_filepath", None)
            need_load = already not in (filepath, prepared)
            if need_load:
                viewer.update_options(self.window_settings.get_view_settings())
                self._copy_template_engine_to_viewer(viewer)
                # Secondary shares primary prepared temp. retain_prepared bumps
                # refs; on success viewer keeps it via _prepared_path; on False
                # return load_file already released the shared path.
                if prepared and prepared != filepath:
                    retained = bool(retain_prepared(prepared))
                viewer.load_file(filepath, prepared_path=prepared)
                retained = False
            # Camera always follows the active tab when available.
            if active is not None and active.loaded:
                state = active.viewer.get_camera_state()
                if state is not None:
                    viewer.set_camera_state(state)
        except Exception as exc:
            if retained and prepared:
                release_prepared(prepared)
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
            # Skin-weights heat is window-global — restore owner tab first.
            handoff = getattr(self, "_handoff_skin_weights_on_tab_change", None)
            if callable(handoff):
                handoff()
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
        unblock = getattr(self, "_unblock_reload_if_idle", None)
        if callable(unblock):
            unblock()

    def on_tab_close_page(self, tab_view, page):
        tab = page.get_child()
        closing_viewer = tab.viewer if isinstance(tab, ViewerTab) else None
        was_selected = self.tab_view.get_selected_page() == page
        if isinstance(tab, ViewerTab):
            self._push_closed_tab(tab)

        # Block notify::selected-page re-entrancy while pages reshuffle.
        self._switching_tab = True
        created_empty = False
        try:
            if was_selected:
                self._unbind_animation_controls(closing_viewer)

            self.tab_view.close_page_finish(page, True)
            if isinstance(tab, ViewerTab):
                self._cancel_warm_load(tab)
                # Drop window-owned heat pointer if this tab owns it (or is active).
                heat = getattr(self, "_skin_weights_heat_temp", None)
                owns_heat = False
                if heat:
                    try:
                        owns_heat = tab.viewer.get_prepared_path() == heat
                    except Exception as exc:
                        self.logger.debug("tab close heat probe: %s", exc)
                if was_selected or owns_heat:
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

