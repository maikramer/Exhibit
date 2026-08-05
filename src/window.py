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

import logging
import os
from pathlib import Path

from gi.repository import Adw, Exb, Gdk, Gio, GLib, GObject, Gtk

from gettext import gettext as _

from .config import *
from .file_patterns import image_patterns
from .periodic_checker import PeriodicChecker
from .settings_manager import WindowSettings
from .widgets.file_row import FileRow
from .widgets.f3d_viewer import F3DViewer
from .widgets.settings_dialog import SettingsDialog
from .widgets.theme_switcher import ThemeSwitcher
from .window_animation import AnimationMixin
from .window_chrome import ChromeMixin
from .window_export import ExportMixin
from .window_file_watch import FileWatchMixin
from .window_inspect import InspectMixin
from .window_layout import LayoutMixin
from .window_lifecycle import LifecycleMixin
from .window_load import LoadMixin
from .window_object_tree import ObjectTreeMixin
from .window_preferences import PreferencesMixin
from .window_settings_io import SettingsIOMixin
from .window_settings_react import SettingsReactMixin
from .window_settings_ui import SettingsUIMixin
from .window_tabs import TabsMixin

GObject.type_register(Exb.View)
GObject.type_register(Exb.Engine)
GObject.type_register(Exb.Blending)
GObject.type_register(Exb.Sprites)
GObject.type_register(Exb.AntiAliasing)
GObject.type_register(Exb.Direction)
GObject.type_register(SettingsDialog)
GObject.type_register(FileRow)

log = logging.getLogger(__name__)


def _hoist_template_callbacks(cls):
    """Expose ``Gtk.Template.Callback`` handlers declared in mixins.

    PyGObject only scans the decorated class namespace, so handlers living in
    base classes stay unresolved; GtkBuilder then aborts the template and
    silently discards every ``<style>`` block in the .ui file.

    Multi-doc: LoadMixin honors gschema focus-existing-tab (samefile / focus).
    Secondary opens use TabsMixin._add_viewer_tab (not _open_in_new_tab stub).
    """
    for base in cls.__mro__[1:]:
        for name, value in vars(base).items():
            if type(value).__name__ != "CallThing" or name in vars(cls):
                continue
            setattr(cls, name, value)
    return cls


class ExbWindow(
    TabsMixin,
    AnimationMixin,
    ObjectTreeMixin,
    SettingsIOMixin,
    SettingsReactMixin,
    SettingsUIMixin,
    PreferencesMixin,
    LoadMixin,
    LayoutMixin,
    ChromeMixin,
    LifecycleMixin,
    InspectMixin,
    FileWatchMixin,
    ExportMixin,
    Adw.ApplicationWindow,
):
    __gtype_name__ = "ExbWindow"

    settings_dialog = Gtk.Template.Child()
    split_view = Gtk.Template.Child()
    sidebar_stack = Gtk.Template.Child()
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
    point_up_switch = Gtk.Template.Child()
    model_scivis_component_combo = Gtk.Template.Child()
    startup_stack = Gtk.Template.Child()
    settings_section = Gtk.Template.Child()
    animation_combo_model = Gtk.Template.Child()
    animation_group = Gtk.Template.Child()
    animation_combo = Gtk.Template.Child()
    animation_time_scale = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    loading_status_page = Gtk.Template.Child()
    primary_menu_button = Gtk.Template.Child()
    home_button_headerbar = Gtk.Template.Child()
    sidebar_toggle_button = Gtk.Template.Child()
    recent_files_box = Gtk.Template.Child()
    recent_files_list = Gtk.Template.Child()
    clear_recent_button = Gtk.Template.Child()
    armature_switch = Gtk.Template.Child()
    checkerboard_switch = Gtk.Template.Child()
    normal_glyphs_switch = Gtk.Template.Child()
    normal_glyphs_scale_spin = Gtk.Template.Child()
    display_depth_switch = Gtk.Template.Child()
    skin_weights_switch = Gtk.Template.Child()
    skin_weights_mode_combo = Gtk.Template.Child()
    skin_weights_joint_combo = Gtk.Template.Child()
    stats_overlay_switch = Gtk.Template.Child()
    automatic_settings_switch = Gtk.Template.Child()
    restore_session_switch = Gtk.Template.Child()
    focus_existing_tab_switch = Gtk.Template.Child()
    automatic_reload_switch = Gtk.Template.Child()
    use_color_switch = Gtk.Template.Child()
    tab_view = Gtk.Template.Child()
    tab_bar = Gtk.Template.Child()
    viewport_overlay = Gtk.Template.Child()
    seed_holder = Gtk.Template.Child()
    object_tree_overlay_shell = Gtk.Template.Child()
    object_tree_toggle = Gtk.Template.Child()
    object_tree_revealer = Gtk.Template.Child()
    object_tree_panel = Gtk.Template.Child()
    object_tree_view = Gtk.Template.Child()
    split_compare_main_paned = Gtk.Template.Child()
    split_compare_revealer = Gtk.Template.Child()
    split_compare_paned = Gtk.Template.Child()
    split_compare_primary_label = Gtk.Template.Child()
    split_compare_pin_check = Gtk.Template.Child()
    split_compare_swap_button = Gtk.Template.Child()
    split_compare_stub = Gtk.Template.Child()

    width = 600
    height = 600
    distance = 0

    @property
    def logger(self):
        return log

    def __init__(self, application=None, startup_filepath=None):
        super().__init__(application=application)

        self.logger  # ensure property is available early
        self.applying_breakpoint = False
        self.block_reload = True
        self._anim_bindings = []
        self._playing_handler_id = 0
        self._switching_tab = False
        self._block_object_tree = False
        self._object_tree_row_handlers = {}
        self._scene_tree_roots = []
        self._mesh_stats = None
        self._armature_xray_restore = None
        self._depth_opacity_restore = None
        self._skin_weights_scivis_restore = None
        self._skin_weights_base_path = None
        self._skin_weights_heat_temp = None
        self._skin_weights_joints = []
        self._closed_tabs = []
        self._tab_menu_page = None
        self._pending_open_paths = []
        self.filepath = ""
        self.file_name = ""
        self.no_file_loaded = True
        self._cached_time_stamp = 0

        self.window_settings = WindowSettings()
        self.saved_settings = Gio.Settings.new("io.github.nokse22.Exhibit")
        self.configurations = {}

        # Scrubber Scale is template child; adj comes from active Exb.Engine.
        self.loading_label = Gtk.Label()
        self.animation_time_adj = Gtk.Adjustment(
            lower=0, upper=1, value=0, step_increment=1
        )
        self.error_status_page = None

        data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share", "exhibit"
        )
        self.hdri_path = os.path.join(data_home, "HDRIs") + "/"
        self.hdri_thumbnails_path = self.hdri_path + "thumbnails/"
        self.user_configurations_path = (
            os.path.join(data_home, "configurations") + "/"
        )
        self.configs_path = self.user_configurations_path
        os.makedirs(self.user_configurations_path, exist_ok=True)
        os.makedirs(os.path.join(data_home, "other files"), exist_ok=True)

        Path(PRESETS_PATH).mkdir(parents=True, exist_ok=True)
        self.presets = Exb.Presets.new_with_paths([PRESETS_PATH])

        # Seed tab 0 before settings/session touch f3d_viewer.
        self._viewport_overlay = self.viewport_overlay
        self._split_compare_stub = self.split_compare_stub
        self.split_compare_main_paned.connect(
            "notify::position", self._on_split_compare_sash_changed
        )
        self.tab_view.connect("close-page", self.on_tab_close_page)
        self.tab_view.connect(
            "notify::selected-page", self.on_tab_selected_page
        )
        self._setup_tab_context_menu()
        self._setup_object_tree_view()
        self._seed_primary_tab()
        self._update_tab_bar_visibility()
        self.logger.info("Declarative shell ready")

        self.change_checker = PeriodicChecker(
            self.periodic_check_for_file_change
        )

        self._setup_window_actions()

        try:
            self.setup_configurations()
        except Exception as exc:
            self.logger.warning("setup_configurations: %s", exc)
            if not self.configurations:
                self.configurations = {}

        self.setup_hdri_folder()

        self.view_drop_target.set_gtypes([Gdk.FileList])
        self.loading_drop_target.set_gtypes([Gdk.FileList])

        self.set_default_size(
            self.saved_settings.get_int("startup-width"),
            self.saved_settings.get_int("startup-height"),
        )
        sidebar_show = self.saved_settings.get_boolean("startup-sidebar-show")
        self.split_view.set_show_sidebar(sidebar_show)
        self.window_settings.set_setting("sidebar-show", sidebar_show)

        # FileRow.file is bound to engine.hdri-file in window.ui (upstream).
        self.hdri_file_row.file_patterns = image_patterns
        self.hdri_file_row.window = self
        for filename in list_files(self.hdri_path):
            filepath = self.hdri_path + filename
            try:
                self.hdri_file_row.add_suggested_file(filepath)
            except Exception:
                self.logger.warning(
                    "Couldn't open HDRI file %s, skipping", filepath
                )

        self.style_manager = Adw.StyleManager.get_default()
        self.style_manager.connect(
            "notify::dark", self.update_background_color
        )
        self.update_background_color()

        self.play_button.connect("clicked", self.on_play_button_clicked)

        self._ensure_app_theme_action()
        self._init_home_button()
        self._init_preferences_actions()
        self._wire_primary_menu_theme()
        self._wire_fork_settings_widgets()

        self.window_settings.connect(
            "changed-view", self.on_view_setting_changed
        )
        self.window_settings.connect(
            "changed-other", self.on_other_setting_changed
        )
        self.window_settings.connect(
            "changed-internal", self.on_internal_setting_changed
        )

        self._block_animation_combo = False
        self.animation_combo.connect(
            "notify::selected", self.on_animation_combo_changed
        )
        try:
            self._bind_animation_controls(self.f3d_viewer)
        except Exception as exc:
            self.logger.debug("bind animation: %s", exc)

        self.block_reload = True
        self.window_settings.sync_all_settings()
        try:
            self._update_all_viewers_options(
                self.window_settings.get_view_settings()
            )
        except Exception as exc:
            self.logger.debug("sync view settings: %s", exc)
        # Template engine binds may have synced light-intensity=0 before F3D
        # init — re-assert WindowSettings lighting onto the bound engine.
        try:
            li = self.window_settings.get_setting("light-intensity").value
            self.engine.set_property("light-intensity", float(li))
            ha = bool(self.window_settings.get_setting("hdri-ambient").value)
            self.engine.set_property("hdri-ambient", ha)
        except Exception as exc:
            self.logger.debug("reassert lighting: %s", exc)
        self._wire_engine_option_fanout()
        self.block_reload = False

        self._apply_nav_settings_from_gschema()

        self.connect("notify::is-active", self.on_window_is_active)

        self._armature_xray_restore = None
        try:
            self.engine.connect(
                "notify::show-armature", self._on_show_armature_changed
            )
        except Exception as exc:
            self.logger.debug("armature notify: %s", exc)

        if startup_filepath:
            self.logger.info("startup file detected: %s", startup_filepath)
            path = (
                startup_filepath
                if isinstance(startup_filepath, str)
                else startup_filepath.get_path()
            )
            self.load_file(filepath=path)
        else:
            self._restore_session_files()

        GLib.timeout_add(250, self._maybe_restore_split_compare)
        self.logger.info("Started")

    # ------------------------------------------------------------------
    # Declarative shell (window.ui) — no runtime chrome rebuild
    # ------------------------------------------------------------------

    def _seed_primary_tab(self) -> None:
        """Move template ExbView into tab 0 without reparenting ToolbarView tree."""
        if self.tab_view.get_n_pages() > 0:
            return
        view = self.viewer
        holder = self.seed_holder
        # Detach seed box (still holding the view) from the overlay first.
        try:
            if holder.get_parent() is self.viewport_overlay:
                self.viewport_overlay.remove_overlay(holder)
        except Exception as exc:
            self.logger.debug("seed_holder overlay remove: %s", exc)
        if view.get_parent() is holder:
            holder.remove(view)
        elif view.get_parent() is not None:
            view.unparent()
        bridge = F3DViewer(view=view)
        self._add_viewer_tab(title=_("Untitled"), select=True, viewer=bridge)

    def _wire_fork_settings_widgets(self) -> None:
        """Wire fork-only sidebar widgets (not bound to Exb.Engine in .ui)."""
        switches = [
            (self.automatic_settings_switch, "auto-best"),
            (self.automatic_reload_switch, "auto-reload"),
            (self.use_color_switch, "use-color"),
            (self.armature_switch, "armature-enable"),
            (self.checkerboard_switch, "checkerboard-enable"),
            (self.normal_glyphs_switch, "normal-glyphs"),
            (self.display_depth_switch, "display-depth"),
            (self.skin_weights_switch, "skin-weights"),
            (self.stats_overlay_switch, "stats-overlay"),
            (self.point_up_switch, "point-up"),
        ]
        for switch, name in switches:
            switch.connect("notify::active", self.on_switch_toggled, name)
            setting = self.window_settings.get_setting(name)
            setting.connect("changed", self.set_switch_to, switch)
            setting.connect("changed-no-ui-update", self.set_switch_to, switch)
            # Seed widget from setting (point-up no longer UI-bound to viewer).
            self.set_switch_to(setting, name, None, switch)

        self.up_direction_combo.connect(
            "notify::selected", self.on_up_direction_combo_changed
        )
        up_setting = self.window_settings.get_setting("up")
        up_setting.connect("changed", self.set_up_direction_combo)
        up_setting.connect("changed-no-ui-update", self.set_up_direction_combo)
        self.set_up_direction_combo(up_setting)

        self.normal_glyphs_scale_spin.connect(
            "notify::value", self.on_spin_changed, "normal-glyphs-scale"
        )
        self.window_settings.get_setting("normal-glyphs-scale").connect(
            "changed", self.set_spin_to, self.normal_glyphs_scale_spin
        )

        self.skin_weights_mode_combo.connect(
            "notify::selected", self.on_skin_weights_mode_combo_changed
        )
        self.skin_weights_joint_combo.connect(
            "notify::selected", self.on_skin_weights_joint_combo_changed
        )
        self.window_settings.get_setting("skin-weights-mode").connect(
            "changed", self.set_skin_weights_mode_combo
        )
        self.window_settings.get_setting("skin-weights").connect(
            "changed", lambda *_: self._refresh_skin_weights_joint_combo()
        )

        self.window_settings.set_setting(
            "auto-best", self.saved_settings.get_boolean("auto-best")
        )
        # Mirror auto-best: gschema key existed but was never seeded/persisted.
        self.window_settings.set_setting(
            "auto-reload", self.saved_settings.get_boolean("auto-reload")
        )
        self.window_settings.set_setting(
            "use-color", self.saved_settings.get_boolean("use-color")
        )
        self.saved_settings.bind(
            "restore-session",
            self.restore_session_switch,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )
        self.restore_session_switch.connect(
            "notify::active", self.on_restore_session_toggled
        )
        self.saved_settings.bind(
            "focus-existing-tab",
            self.focus_existing_tab_switch,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )
        self._refresh_recent_files_ui()

    def _setup_window_actions(self) -> None:
        """Register window Gio actions and keyboard accelerators."""
        self.save_as_action = self.create_action(
            "save-as-image", self.open_save_file_chooser
        )
        self.open_new_action = self.create_action(
            "open-new", self.open_file_chooser
        )
        self.create_action("add-new", self.open_file_chooser)
        self.create_action("open-folder", self.open_folder_chooser)

        self.orthographic_action = Gio.SimpleAction.new_stateful(
            "orthographic",
            None,
            GLib.Variant(
                "b", self.window_settings.get_setting("orthographic").value
            ),
        )
        self.orthographic_action.connect(
            "change-state", self.orthographic_state_changed
        )
        self.window_settings.get_setting("orthographic").connect(
            "changed", self.on_orthographic_changed
        )
        self.add_action(self.orthographic_action)

        self._camera_sync = False
        self._syncing_cameras = False
        self.sync_cameras_action = Gio.SimpleAction.new_stateful(
            "sync-cameras", None, GLib.Variant("b", False)
        )
        self.sync_cameras_action.connect(
            "change-state", self._on_sync_cameras_change
        )
        self.add_action(self.sync_cameras_action)

        self._split_compare = False
        self._split_compare_pinned = False
        self._split_compare_pin_filepath = None
        self._split_compare_pin_prepared = None
        self._split_compare_sizing = False
        self._split_compare_sash_save_id = 0
        self._split_compare_restoring = False
        self._split_restore_attempts = 0
        self.split_compare_action = Gio.SimpleAction.new_stateful(
            "split-compare", None, GLib.Variant("b", False)
        )
        self.split_compare_action.connect(
            "change-state", self._on_split_compare_change
        )
        self.add_action(self.split_compare_action)
        self.split_compare_swap_action = Gio.SimpleAction.new(
            "split-compare-swap", None
        )
        self.split_compare_swap_action.connect(
            "activate", self._on_split_compare_swap
        )
        self.split_compare_swap_action.set_enabled(False)
        self.add_action(self.split_compare_swap_action)

        pin = getattr(self, "split_compare_pin_check", None)
        if pin is not None:
            pin.connect("notify::active", self._on_split_compare_pin_toggled)
        main_paned = getattr(self, "split_compare_main_paned", None)
        if main_paned is not None:
            main_paned.connect(
                "notify::position", self._on_split_compare_sash_changed
            )

        self.settings_action = Gio.SimpleAction.new_stateful(
            "settings",
            GLib.VariantType.new("s"),
            GLib.Variant("s", "general"),
        )
        self.settings_action.connect(
            "change-state",
            lambda _action, state: self.change_setting_state(state),
        )
        self.add_action(self.settings_action)

        self.save_settings_action = self.create_action(
            "save-settings", self.on_save_settings
        )
        self.save_settings_action.set_enabled(False)

        view_map = {
            "view-front": "front_view",
            "view-right": "right_view",
            "view-back": "back_view",
            "view-left": "left_view",
            "view-top": "top_view",
            "view-isometric": "isometric_view",
        }
        for action_name, method_name in view_map.items():
            self.create_action(
                action_name,
                lambda *_a, m=method_name: self._invoke_viewer_view(m),
            )

        inspect = getattr(self, "_apply_skin_weights_mode", None)
        if callable(inspect):
            self.create_action(
                "inspect-skin-weights",
                self._on_inspect_skin_weights_action,
            )

        app = self.get_application()
        if app is not None:
            app.set_accels_for_action("win.sync-cameras", ["<Primary><Shift>c"])
            app.set_accels_for_action("win.open-new", ["<Primary>o"])
            app.set_accels_for_action(
                "win.open-folder", ["<Primary><Shift>o"]
            )
            app.set_accels_for_action(
                "win.split-compare", ["<Primary><Shift>d"]
            )
            app.set_accels_for_action(
                "win.split-compare-swap", ["<Primary><Shift>x"]
            )
            for action, accel in (
                ("win.view-front", ["1"]),
                ("win.view-right", ["3"]),
                ("win.view-back", ["<Shift>1"]),
                ("win.view-left", ["<Shift>3"]),
                ("win.view-top", ["7"]),
                ("win.view-isometric", ["<Shift>7"]),
                ("win.orthographic", ["5"]),
            ):
                app.set_accels_for_action(action, accel)

    def _invoke_viewer_view(self, method_name: str) -> None:
        try:
            viewer = self.f3d_viewer
        except Exception:
            return
        method = getattr(viewer, method_name, None)
        if callable(method):
            method()

    def _on_inspect_skin_weights_action(self, *_args) -> None:
        setting = self.window_settings.get_setting("skin-weights")
        self.window_settings.set_setting("skin-weights", not bool(setting.value))

    def _wire_primary_menu_theme(self) -> None:
        """Upstream: ThemeSwitcher as custom child of primary menu popover."""
        btn = getattr(self, "primary_menu_button", None)
        if btn is None:
            return
        popover = btn.get_popover()
        if popover is None:
            return
        try:
            popover.add_child(ThemeSwitcher(), "theme")
        except Exception as exc:
            self.logger.debug("theme switcher wire failed: %s", exc)

    def _ensure_app_theme_action(self) -> None:
        app = self.get_application()
        if app is None or app.lookup_action("theme") is not None:
            return
        theme = "auto"
        try:
            theme = app.saved_settings.get_string("theme")
        except Exception:
            pass
        if theme in ("default", "follow"):
            theme = "auto"
        if theme not in ("auto", "light", "dark"):
            theme = "auto"
        action = Gio.SimpleAction.new_stateful(
            "theme",
            GLib.VariantType.new("s"),
            GLib.Variant("s", theme),
        )
        action.connect("activate", self._on_app_theme_changed)
        action.connect("change-state", self._on_app_theme_changed)
        app.add_action(action)
        self._apply_theme_string(theme)

    def _on_app_theme_changed(self, action, state):
        if state is None:
            return
        value = state.get_string()
        if value in ("default", "follow"):
            value = "auto"
        if value not in ("auto", "light", "dark"):
            return
        action.set_state(GLib.Variant("s", value))
        app = self.get_application()
        if app is not None and hasattr(app, "saved_settings"):
            app.saved_settings.set_string("theme", value)
        self._apply_theme_string(value)
        sync = getattr(self, "_sync_theme_toggle_button", None)
        if callable(sync):
            sync()

    @staticmethod
    def _apply_theme_string(value: str) -> None:
        manager = Adw.StyleManager.get_default()
        match value:
            case "auto" | "follow":
                manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
            case "light":
                manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            case "dark":
                manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def _apply_nav_settings_from_gschema(self) -> None:
        """Load nav prefs from GSettings into WindowSettings and viewers."""
        load = getattr(self, "_load_nav_settings_from_gschema", None)
        if callable(load):
            load()
            return
        opts = self._nav_settings_dict()
        try:
            self.f3d_viewer.apply_nav_settings(opts)
        except Exception as exc:
            self.logger.debug("nav apply: %s", exc)

    def _on_show_armature_changed(self, engine, *_pspec):
        """Keep WindowSettings in sync when Exb show-armature flips externally."""
        try:
            enabled = bool(engine.get_property("show-armature"))
        except Exception:
            return
        try:
            current = bool(
                self.window_settings.get_setting("armature-enable").value
            )
            if current != enabled:
                self.window_settings.set_setting(
                    "armature-enable", enabled, False
                )
        except Exception as exc:
            self.logger.debug("armature setting sync: %s", exc)

    # ------------------------------------------------------------------
    # Exb / mixin glue kept on the window
    # ------------------------------------------------------------------

    def create_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        return action

    def update_background_color(self, *args):
        """Theme bg → Exb.Engine directly (avoid F3D string/locale pitfalls)."""
        use_color = False
        try:
            use_color = bool(
                self.window_settings.get_setting("use-color").value
            )
        except Exception:
            pass

        rgba = Gdk.RGBA()
        if use_color:
            try:
                value = self.window_settings.get_setting("bg-color").value
                rgba.red = float(value[0])
                rgba.green = float(value[1])
                rgba.blue = float(value[2])
                rgba.alpha = 1.0
            except Exception:
                rgba.parse("#1e1e1e")
        elif self.style_manager.get_dark():
            rgba.red = rgba.green = rgba.blue = 0.117
            rgba.alpha = 1.0
        else:
            rgba.red = rgba.green = rgba.blue = 1.0
            rgba.alpha = 1.0

        try:
            self.engine.set_property("background-color", rgba)
        except Exception as exc:
            self.logger.debug("engine bg: %s", exc)
        try:
            self._update_all_viewers_options(
                {"bg-color": [rgba.red, rgba.green, rgba.blue]}
            )
        except Exception as exc:
            self.logger.debug("viewers bg: %s", exc)

    def set_propertys_from_name(self, name):
        """Apply an Exb.Presets .ini entry by key (engine props only)."""
        if not name or name == "custom":
            return
        try:
            preset = self.presets.lookup(name)
        except Exception as exc:
            self.logger.debug("presets.lookup(%s): %s", name, exc)
            preset = None
        if preset is None:
            return
        try:
            self.engine.apply_preset(preset)
        except Exception as exc:
            self.logger.warning("apply_preset(%s): %s", name, exc)
        for tab in self._iter_tabs():
            eng = getattr(tab.viewer, "engine", None)
            if eng is None or eng is self.engine:
                continue
            try:
                eng.apply_preset(preset)
            except Exception as exc:
                self.logger.debug("tab apply_preset: %s", exc)

    def change_setting_state(self, state):
        self.logger.debug("Requested changing settings to %s", state)

        if state.get_string() == "custom":
            self.save_settings_action.set_enabled(True)
            self.settings_action.set_state(state)
            return

        name = state.get_string()
        # Exb .ini preset first, then JSON/WindowSettings so app defaults win
        # (general.ini must not leave roughness=1.0 / dim lights stuck).
        self.set_propertys_from_name(name)
        if name in getattr(self, "configurations", {}):
            self.set_settings_from_name(name)

        self.settings_action.set_state(state)
        self.save_settings_action.set_enabled(False)
        self.update_background_color()

    def load_file(self, file=None, **kwargs):
        """Accept Gio.File / path positional and forward to LoadMixin."""
        if file is not None and not kwargs.get("filepath"):
            if isinstance(file, Gio.File):
                kwargs["filepath"] = file.get_path() or ""
            elif isinstance(file, str):
                kwargs["filepath"] = file
        return LoadMixin.load_file(self, **kwargs)

    @Gtk.Template.Callback("enum_name")
    def enum_name(self, item):
        return item.get_nick().title().replace("-", " ")


ExbWindow = Gtk.Template(
    resource_path="/io/github/nokse22/Exhibit/window.ui"
)(_hoist_template_callbacks(ExbWindow))


def list_files(directory):
    if not os.path.isdir(directory):
        return []
    items = os.listdir(directory)
    return [
        item
        for item in items
        if os.path.isfile(os.path.join(directory, item))
    ]
