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
from .mesh_stats import collect_mesh_stats, format_overlay_text
from .periodic_checker import PeriodicChecker
from .widgets.viewer_tab import ViewerTab
from .widgets.f3d_viewer import F3DViewer
from .window_object_tree import ObjectTreeMixin
from .recent_files import push_recent
from .session_files import collect_session_paths, session_paths_to_restore

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
class ExbWindow(ObjectTreeMixin, Adw.ApplicationWindow):
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
        return self._viewer_bridge

    @property
    def logger(self):
        return log

    def __init__(self, application=None, startup_filepath=None):
        super().__init__(application=application)

        # Flags
        self.applying_breakpoint = False
        self.block_reload = True
        self._block_object_tree = False
        self._object_tree_row_handlers = {}
        self._viewer_bridge = F3DViewer(view=self.viewer)

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

        # Fork: mesh stats HUD + external file-change poller (single doc).
        self._stats_overlay = Gtk.Label(
            visible=False,
            halign=Gtk.Align.START,
            valign=Gtk.Align.END,
            margin_start=16,
            margin_bottom=16,
            xalign=0,
            selectable=True,
        )
        self._stats_overlay.add_css_class("stats-overlay")
        parent = self.viewer.get_parent()
        if isinstance(parent, Gtk.Overlay):
            parent.add_overlay(self._stats_overlay)
        else:
            log.debug("stats overlay: viewer parent is not Gtk.Overlay")

        self._file_checker = PeriodicChecker(self._periodic_check_file_change)
        self._auto_reload = True
        try:
            self._auto_reload = settings.get_boolean("auto-reload")
        except Exception:
            pass

        self._setup_minimal_tabs()
        self._setup_minimal_outliner()
        self._apply_nav_settings_from_gschema()
        self._armature_xray_restore = None
        try:
            self.engine.connect(
                "notify::show-armature", self._on_show_armature_changed
            )
        except Exception as exc:
            log.debug("armature notify: %s", exc)

        if startup_filepath:
            log.info(f"startup file detected: {startup_filepath}")
            # upstream passes path string; normalize to Gio.File
            if isinstance(startup_filepath, str):
                self.load_file(Gio.File.new_for_path(startup_filepath))
            else:
                self.load_file(startup_filepath)
        else:
            self._restore_session_if_enabled()

        log.info("Started")

    def _setup_minimal_tabs(self):
        """Wrap the template ExbView in AdwTabView (fork multi-doc v1)."""
        overlay = self.viewer.get_parent()
        if not isinstance(overlay, Gtk.Overlay):
            log.warning("minimal tabs: expected Gtk.Overlay parent")
            self.tab_view = None
            self.tab_bar = None
            return

        # Detach template viewer; keep engine bindings intact.
        overlay.set_child(None)

        self.tab_view = Adw.TabView()
        self.tab_bar = Adw.TabBar(view=self.tab_view, autohide=False)

        # First tab hosts the template viewer/engine (settings stay bound).
        first = Gtk.Overlay()
        first.set_child(self.viewer)
        first_page = self.tab_view.append(first)
        first_page.set_title(_("Untitled"))
        self._primary_tab_page = first_page
        self._tabs_by_page = {first_page: None}  # None = template viewer

        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        shell.append(self.tab_bar)
        shell.append(self.tab_view)
        overlay.set_child(shell)

        self.tab_view.connect("notify::selected-page", self._on_tab_selected)
        self.create_action("new-tab", self._on_new_tab_action)
        self.create_action("inspect-skin-weights", self._on_inspect_skin_weights)
        self.create_action("split-compare-toggle", self._on_split_compare_toggle)

        # Camera preset actions (approximate via Exb rotate until full nav ports).
        self.create_action("view-front", lambda *_: self._apply_named_view("front"))
        self.create_action("view-right", lambda *_: self._apply_named_view("right"))
        self.create_action("view-back", lambda *_: self._apply_named_view("back"))
        self.create_action("view-left", lambda *_: self._apply_named_view("left"))
        self.create_action("view-top", lambda *_: self._apply_named_view("top"))
        self.create_action("view-isometric", lambda *_: self._apply_named_view("isometric"))
        app = self.get_application()
        if app is not None:
            for action, accel in (
                ("win.view-front", ["1"]),
                ("win.view-right", ["3"]),
                ("win.view-back", ["<Shift>1"]),
                ("win.view-left", ["<Shift>3"]),
                ("win.view-top", ["7"]),
                ("win.view-isometric", ["<Shift>7"]),
            ):
                app.set_accels_for_action(action, accel)
        log.info("minimal AdwTabView ready")

    def _apply_named_view(self, name: str) -> None:
        eng = self.engine
        try:
            eng.reset_camera()
            if name == "front":
                pass
            elif name == "right":
                eng.rotate(90.0, 0.0)
            elif name == "back":
                eng.rotate(180.0, 0.0)
            elif name == "left":
                eng.rotate(-90.0, 0.0)
            elif name == "top":
                eng.rotate(0.0, -80.0)
            elif name == "isometric":
                eng.rotate(35.0, -30.0)
        except Exception as exc:
            log.debug("named view %s: %s", name, exc)

    def _on_split_compare_toggle(self, *args):
        """Toggle a secondary Exb viewer beside the tab view."""
        if self.tab_view is None:
            return
        shell = self.tab_view.get_parent()
        if shell is None:
            return

        if getattr(self, "_split_compare_on", False):
            paned = getattr(self, "split_compare_paned", None)
            if paned is not None and paned.get_parent() is shell:
                paned.set_start_child(None)
                paned.set_end_child(None)
                try:
                    shell.remove(paned)
                except Exception:
                    pass
                shell.append(self.tab_view)
            self._split_compare_on = False
            try:
                settings.set_boolean("split-compare-enabled", False)
            except Exception:
                pass
            self.send_toast(_("Split Compare off"))
            return

        if getattr(self, "split_compare_paned", None) is None:
            self.split_compare_paned = Gtk.Paned(
                orientation=Gtk.Orientation.HORIZONTAL
            )
            self.split_compare_paned.set_wide_handle(True)
        if getattr(self, "_split_compare_viewer", None) is None:
            self._split_compare_viewer = F3DViewer()
            self._split_compare_viewer.add_css_class("f3d-render")
            self._split_compare_viewer.set_hexpand(True)
            self._split_compare_viewer.set_vexpand(True)
            drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
            drop.connect("drop", self._on_split_compare_drop)
            self._split_compare_viewer.add_controller(drop)

        try:
            shell.remove(self.tab_view)
        except Exception:
            pass
        self.split_compare_paned.set_start_child(self.tab_view)
        self.split_compare_paned.set_end_child(self._split_compare_viewer)
        shell.append(self.split_compare_paned)
        self._split_compare_on = True
        try:
            settings.set_boolean("split-compare-enabled", True)
            ratio = settings.get_double("split-compare-sash-ratio")
            # Apply sash after allocate
            def _size():
                w = self.split_compare_paned.get_width()
                if w > 0:
                    self.split_compare_paned.set_position(int(w * ratio))
                    return False
                return True
            GLib.timeout_add(50, _size)
        except Exception as exc:
            log.debug("split compare sash: %s", exc)
        self.send_toast(_("Split Compare on"))


    def _on_split_compare_drop(self, _drop, value, _x, _y):
        try:
            files = value.get_files()
        except Exception:
            return False
        if not files:
            return False
        path = files[0].get_path()
        if not path or self._split_compare_viewer is None:
            return False
        ok = self._split_compare_viewer.load_file(path)
        if ok:
            self.send_toast(_("Compare: {}").format(os.path.basename(path)))
        return ok

    def _on_inspect_skin_weights(self, *args):
        """Joint heat map via temp GLB + Exb scivis (picker for joint index)."""
        path = self.filepath
        if not path:
            self.send_toast(_("Open a model first"))
            return
        try:
            from .gltf_scene_graph import _load_gltf, glb_has_skins
            from .skin_weights import list_skin_joints

            if not glb_has_skins(path):
                self.send_toast(_("No skins in this model"))
                return
            source = getattr(self._viewer_bridge, "_prepared_path", None) or path
            gltf = _load_gltf(source, already_prepared=bool(
                getattr(self._viewer_bridge, "_prepared_path", None)
            ))
            joints = list_skin_joints(gltf or {}, skin_index=0)
        except Exception as exc:
            log.warning("skin weight inspect prep failed: %s", exc)
            self.send_toast(_("Skin-weight inspect failed"))
            return

        if not joints:
            self._apply_skin_weight_heat(source, 0)
            return

        dialog = Adw.AlertDialog(
            heading=_("Skin weights"),
            body=_("Pick a joint for the heat map"),
        )
        combo = Gtk.DropDown.new_from_strings(
            [f"{j.list_index}: {j.name}" for j in joints]
        )
        combo.set_selected(0)
        dialog.set_extra_child(combo)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("apply", _("Apply"))
        dialog.set_default_response("apply")

        def _on_response(_d, response):
            if response != "apply":
                return
            idx = int(combo.get_selected())
            joint_i = joints[idx].list_index if 0 <= idx < len(joints) else 0
            self._apply_skin_weight_heat(source, joint_i)

        dialog.connect("response", _on_response)
        dialog.present(self)

    def _apply_skin_weight_heat(self, source: str, joint_list_index: int):
        try:
            from .skin_weights import HEAT_ATTR, write_skin_weight_heat_temp

            temp = write_skin_weight_heat_temp(source, joint_list_index)
        except Exception as exc:
            log.warning("skin weight heat failed: %s", exc)
            self.send_toast(_("Skin-weight inspect failed"))
            return

        try:
            self.engine.reset()
            self.engine.load_file(Gio.File.new_for_path(temp))
            try:
                self.engine.set_property("scivis-array-name", HEAT_ATTR)
                self.engine.set_property("scivis", True)
            except Exception as exc:
                log.debug("scivis props: %s", exc)
            prev = getattr(self, "_skinw_temp", None)
            if prev and prev != temp:
                try:
                    os.unlink(prev)
                except OSError:
                    pass
            self._skinw_temp = temp
            self.send_toast(
                _("Skin weights (joint {})").format(joint_list_index)
            )
        except Exception as exc:
            log.warning("skin weight load failed: %s", exc)
            try:
                os.unlink(temp)
            except OSError:
                pass
            self.send_toast(_("Skin-weight inspect failed"))

    def _on_tab_selected(self, *args):
        page = self.tab_view.get_selected_page() if self.tab_view else None
        if page is None:
            return
        child = page.get_child()
        if isinstance(child, ViewerTab) and child.filepath:
            self.filepath = child.filepath
            self.file_name = child.file_name
            self.set_title(_("Exhibit - {}").format(self.file_name))
            self.title_widget.set_subtitle(self.file_name)
        elif page is getattr(self, "_primary_tab_page", None) and self.filepath:
            self.set_title(_("Exhibit - {}").format(self.file_name))
            self.title_widget.set_subtitle(self.file_name)

    def _on_new_tab_action(self, *args):
        self.open_file_chooser()

    def _apply_nav_settings_from_gschema(self):
        """Push fork nav prefs onto Exb.View (invert / sensitivity / modifiers)."""
        try:
            self.viewer.set_property(
                "invert-x", settings.get_boolean("nav-invert-x")
            )
            self.viewer.set_property(
                "invert-y", settings.get_boolean("nav-invert-y")
            )
            self.viewer.set_property(
                "orbit-sensitivity",
                settings.get_double("nav-orbit-sensitivity"),
            )
            self.viewer.set_property(
                "zoom-sensitivity",
                settings.get_double("nav-zoom-sensitivity"),
            )
            self.viewer.set_property(
                "pan-sensitivity",
                settings.get_double("nav-pan-sensitivity"),
            )
        except Exception as exc:
            log.debug("nav settings: %s", exc)

    def _on_show_armature_changed(self, engine, *_pspec):
        """X-ray-ish: lower mesh opacity while armature overlay is on."""
        try:
            enabled = bool(engine.get_property("show-armature"))
        except Exception:
            return
        try:
            if enabled:
                if self._armature_xray_restore is None:
                    self._armature_xray_restore = float(
                        engine.get_property("model-opacity")
                    )
                engine.set_property("model-opacity", 0.35)
            elif self._armature_xray_restore is not None:
                engine.set_property("model-opacity", self._armature_xray_restore)
                self._armature_xray_restore = None
        except Exception as exc:
            log.debug("armature xray: %s", exc)

    def _setup_minimal_outliner(self):
        """Floating outliner panel over the viewport (fork ObjectTreeMixin)."""
        overlay = self.viewer.get_parent()
        # After tabs setup, overlay child is shell; find Gtk.Overlay ancestor.
        widget = self.viewer
        overlay = None
        while widget is not None:
            parent = widget.get_parent()
            if isinstance(parent, Gtk.Overlay):
                overlay = parent
                break
            widget = parent
        if overlay is None:
            log.warning("outliner: no Gtk.Overlay found")
            return

        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        rail.add_css_class("viewport-tool-rail")
        sidebar_btn = Gtk.ToggleButton(
            icon_name="sidebar-show-symbolic",
            tooltip_text=_("Toggle Sidebar"),
        )
        sidebar_btn.add_css_class("overlay-button")
        sidebar_btn.add_css_class("circular")
        sidebar_btn.set_active(self.split_view.get_show_sidebar())
        self.split_view.bind_property(
            "show-sidebar",
            sidebar_btn,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        home_btn = Gtk.Button(
            icon_name="go-home-symbolic",
            tooltip_text=_("Reset to Bounds"),
        )
        home_btn.add_css_class("overlay-button")
        home_btn.add_css_class("circular")
        home_btn.connect("clicked", self.on_home_clicked)
        rail.append(sidebar_btn)
        rail.append(home_btn)

        self.object_tree_toggle = Gtk.ToggleButton(
            icon_name="view-list-symbolic",
            tooltip_text=_("Outliner"),
            visible=False,
        )
        self.object_tree_toggle.add_css_class("overlay-button")
        self.object_tree_toggle.add_css_class("circular")
        rail.append(self.object_tree_toggle)

        self.object_tree_view = Gtk.ListView()
        self.object_tree_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.object_tree_panel.add_css_class("object-tree-overlay-panel")
        scroll = Gtk.ScrolledWindow(
            min_content_width=220,
            max_content_height=360,
            child=self.object_tree_view,
        )
        self.object_tree_panel.append(scroll)

        revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT,
            child=self.object_tree_panel,
        )
        revealer.bind_property(
            "reveal-child",
            self.object_tree_toggle,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        shell.add_css_class("object-tree-overlay-shell")
        shell.set_valign(Gtk.Align.START)
        shell.set_halign(Gtk.Align.START)
        shell.set_margin_start(12)
        shell.set_margin_top(48)
        shell.append(rail)
        shell.append(revealer)
        overlay.add_overlay(shell)

        self._setup_object_tree_view()
        log.info("minimal outliner ready")

    def _open_in_new_tab(self, file: Gio.File) -> bool:
        """Load model into a new ViewerTab (secondary engines)."""
        if self.tab_view is None:
            return False
        path = file.get_path()
        if not path:
            return False
        tab = ViewerTab()
        page = self.tab_view.append(tab)
        page.set_title(os.path.basename(path))
        self._tabs_by_page[page] = tab
        self.tab_view.set_selected_page(page)

        # Warm prepare on a worker, then load on the UI thread.
        self.block_reload = True
        self.loading_status_page.set_description(
            _("Loading {}").format(os.path.basename(path)))

        def _prepare():
            try:
                load_path, _legacy = prepare_glb_for_load(path)
                return load_path
            except Exception as exc:
                log.warning("warm prepare failed: %s", exc)
                return path

        def _finish(load_path):
            ok = tab.viewer.load_file(path, prepared_path=load_path)
            self.block_reload = False
            if not ok:
                self.tab_view.close_page(page)
                self.send_toast(_("Can't open") + " " + os.path.basename(path))
                return False
            tab.filepath = path
            tab.file_name = os.path.basename(path)
            tab.loaded = True
            self.filepath = path
            self.file_name = tab.file_name
            self.no_file_loaded = False
            self.stack.set_visible_child_name("3d_page")
            self._update_stats_overlay()
            self._remember_recent(path)
            return False

        def _worker():
            load_path = _prepare()
            GLib.idle_add(_finish, load_path)

        threading.Thread(target=_worker, daemon=True).start()
        self.stack.set_visible_child_name("3d_page")
        return True

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

        filepath = file.get_path() or ""

        # Focus existing tab if same path already open.
        if filepath and self.tab_view is not None:
            try:
                focus = settings.get_boolean("focus-existing-tab")
            except Exception:
                focus = True
            if focus:
                for i in range(self.tab_view.get_n_pages()):
                    page = self.tab_view.get_nth_page(i)
                    child = page.get_child()
                    tab_path = ""
                    if isinstance(child, ViewerTab):
                        tab_path = child.filepath
                    elif page is getattr(self, "_primary_tab_page", None):
                        tab_path = self.filepath
                    if tab_path:
                        try:
                            same = os.path.samefile(tab_path, filepath)
                        except OSError:
                            same = os.path.abspath(tab_path) == os.path.abspath(filepath)
                        if same:
                            self.tab_view.set_selected_page(page)
                            return

        # Already have a document → open another tab (fork multi-doc).
        if (
            not self.no_file_loaded
            and self.tab_view is not None
            and self.tab_view.get_n_pages() >= 1
        ):
            if self._open_in_new_tab(file):
                return
            # fall through to primary load on failure

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
        try:
            self._viewer_bridge._prepared_path = self._prepared_load_path
            self._viewer_bridge._loaded_filepath = filepath
            self._viewer_bridge._refresh_scene_graph(
                self._prepared_load_path or filepath
            )
            # Fork default: bind pose (no clip) until user picks an animation.
            self.engine.set_property("animation-index", -1)
        except Exception as exc:
            log.debug("bridge scene graph / bind pose: %s", exc)

        self.on_file_opened()

    def on_file_opened(self):
        log.debug("on file opened")

        self.file_name = os.path.basename(self.filepath)

        self.set_title(_("Exhibit - {}").format(self.file_name))
        self.title_widget.set_subtitle(self.file_name)
        self.stack.set_visible_child_name("3d_page")
        self.viewer.grab_focus()

        self.no_file_loaded = False
        page = getattr(self, "_primary_tab_page", None)
        if page is not None and self.file_name:
            page.set_title(self.file_name)

        self.update_background_color()
        self.update_animation_ui()
        self._update_stats_overlay()
        try:
            self.refresh_object_tree()
        except Exception as exc:
            log.debug("object tree: %s", exc)
        self.update_time_stamp()
        self._remember_recent(self.filepath)
        try:
            self._file_checker.run()
        except Exception as exc:
            log.debug("file checker: %s", exc)

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

    def _remember_recent(self, path: str) -> None:
        if not path:
            return
        try:
            recent = list(settings.get_strv("recent-files"))
            settings.set_strv("recent-files", push_recent(recent, path))
        except Exception as exc:
            log.debug("recent files: %s", exc)

    def _iter_open_paths(self) -> list[str]:
        paths: list[str] = []
        if self.tab_view is None:
            if self.filepath:
                paths.append(self.filepath)
            return paths
        for i in range(self.tab_view.get_n_pages()):
            page = self.tab_view.get_nth_page(i)
            child = page.get_child()
            if isinstance(child, ViewerTab) and child.filepath:
                paths.append(child.filepath)
            elif page is getattr(self, "_primary_tab_page", None) and self.filepath:
                paths.append(self.filepath)
        return paths

    def _persist_session(self) -> None:
        try:
            paths = collect_session_paths(self._iter_open_paths())
            settings.set_strv("session-files", paths)
        except Exception as exc:
            log.debug("session persist: %s", exc)

    def _restore_session_if_enabled(self) -> None:
        try:
            enabled = settings.get_boolean("restore-session")
            paths = session_paths_to_restore(
                enabled, list(settings.get_strv("session-files"))
            )
        except Exception as exc:
            log.debug("session restore read: %s", exc)
            return
        for path in paths:
            self.load_file(Gio.File.new_for_path(path))

    def _file_mtime(self, path):
        if not path:
            return None
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    def update_time_stamp(self):
        mtime = self._file_mtime(self.filepath)
        if mtime is not None:
            self._cached_time_stamp = mtime
        return False

    def _periodic_check_file_change(self):
        if self.block_reload or self.no_file_loaded or not self.filepath:
            return True
        disk_mtime = self._file_mtime(self.filepath)
        if disk_mtime is None:
            return True
        if not self._cached_time_stamp:
            self._cached_time_stamp = disk_mtime
            return True
        if disk_mtime <= self._cached_time_stamp:
            return True
        self._cached_time_stamp = disk_mtime
        auto = getattr(self, "_auto_reload", True)
        try:
            auto = settings.get_boolean("auto-reload")
        except Exception:
            pass
        if auto:
            log.info("auto-reload %s", self.filepath)
            self.load_file(Gio.File.new_for_path(self.filepath))
        else:
            self._prompt_reload_changed_file()
        return True

    def _prompt_reload_changed_file(self):
        if getattr(self, "_reload_dialog_open", False):
            return
        path = self.filepath
        if not path:
            return
        self._reload_dialog_open = True
        dialog = Adw.AlertDialog(
            heading=_("File changed on disk"),
            body=_("Reload {}?").format(os.path.basename(path)),
        )
        dialog.add_response("ignore", _("Ignore"))
        dialog.add_response("reload", _("Reload"))
        dialog.set_response_appearance("reload", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("reload")

        def _on_response(_dialog, response):
            self._reload_dialog_open = False
            if response == "reload":
                self.load_file(Gio.File.new_for_path(path))

        dialog.connect("response", _on_response)
        dialog.present(self)

    def _update_stats_overlay(self):
        label = getattr(self, "_stats_overlay", None)
        if label is None or not self.filepath:
            return
        try:
            stats = collect_mesh_stats(self.filepath)
            text = format_overlay_text(stats)
            label.set_label(text)
            label.set_visible(bool(text))
        except Exception as exc:
            log.debug("stats overlay: %s", exc)
            label.set_visible(False)

    @Gtk.Template.Callback("on_close_request")
    def on_close_request(self, window):
        log.debug("window closed, saving settings")
        try:
            self._file_checker.stop()
        except Exception:
            pass
        self._persist_session()
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
