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

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Gdk, Gio, GLib, GObject, Pango

from . import logger_lib
from .periodic_checker import PeriodicChecker
from .settings_manager import WindowSettings
from .window_tabs import TabsMixin
from .window_animation import AnimationMixin
from .window_object_tree import ObjectTreeItem, ObjectTreeMixin
from .window_settings_ui import SettingsUIMixin, list_to_rgb, rgb_to_list, up_dir_n_to_string, up_dir_string_to_n
from .file_patterns import allowed_extensions, image_patterns

from gettext import gettext as _

_HELP_OVERLAY_RESOURCE = "/io/github/nokse22/Exhibit/gtk/help-overlay.ui"

from .window_load import LoadMixin
from .window_layout import LayoutMixin
from .window_chrome import ChromeMixin
from .window_export import ExportMixin
from .window_file_watch import FileWatchMixin
from .window_inspect import InspectMixin
from .window_lifecycle import LifecycleMixin
from .window_settings_io import SettingsIOMixin
from .window_settings_react import SettingsReactMixin
from .window_preferences import PreferencesMixin


@Gtk.Template(resource_path='/io/github/nokse22/Exhibit/ui/window.ui')
class Viewer3dWindow(
    TabsMixin,
    AnimationMixin,
    ObjectTreeMixin,
    SettingsUIMixin,
    SettingsIOMixin,
    SettingsReactMixin,
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
    __gtype_name__ = 'Viewer3dWindow'

    loading_label = Gtk.Template.Child()
    error_status_page = Gtk.Template.Child()
    recent_files_box = Gtk.Template.Child()
    recent_files_list = Gtk.Template.Child()
    clear_recent_button = Gtk.Template.Child()

    split_view = Gtk.Template.Child()

    title_widget = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    toolbar_view = Gtk.Template.Child()
    tab_view = Gtk.Template.Child()
    tab_bar = Gtk.Template.Child()

    view_drop_target = Gtk.Template.Child()
    loading_drop_target = Gtk.Template.Child()

    toast_overlay = Gtk.Template.Child()
    split_compare_main_paned = Gtk.Template.Child()
    split_compare_revealer = Gtk.Template.Child()
    split_compare_column = Gtk.Template.Child()
    split_compare_paned = Gtk.Template.Child()
    split_compare_pin_check = Gtk.Template.Child()
    split_compare_swap_button = Gtk.Template.Child()
    split_compare_primary_label = Gtk.Template.Child()

    grid_switch = Gtk.Template.Child()
    absolute_grid_switch = Gtk.Template.Child()

    translucency_switch = Gtk.Template.Child()
    tone_mapping_switch = Gtk.Template.Child()
    ambient_occlusion_switch = Gtk.Template.Child()
    anti_aliasing_switch = Gtk.Template.Child()
    hdri_ambient_switch = Gtk.Template.Child()
    light_intensity_spin = Gtk.Template.Child()

    edges_switch = Gtk.Template.Child()
    edges_width_spin = Gtk.Template.Child()

    use_skybox_switch = Gtk.Template.Child()

    hdri_file_row = Gtk.Template.Child()
    blur_switch = Gtk.Template.Child()
    blur_coc_spin = Gtk.Template.Child()

    use_color_switch = Gtk.Template.Child()
    background_color_button = Gtk.Template.Child()

    point_up_switch = Gtk.Template.Child()
    up_direction_combo = Gtk.Template.Child()
    nav_invert_y_switch = Gtk.Template.Child()
    nav_invert_x_switch = Gtk.Template.Child()
    nav_zoom_to_cursor_switch = Gtk.Template.Child()
    nav_orbit_around_cursor_switch = Gtk.Template.Child()
    nav_touchpad_orbit_switch = Gtk.Template.Child()
    nav_mmb_click_pivot_switch = Gtk.Template.Child()
    nav_orbit_sensitivity_spin = Gtk.Template.Child()
    nav_zoom_sensitivity_spin = Gtk.Template.Child()
    nav_pan_sensitivity_spin = Gtk.Template.Child()

    automatic_settings_switch = Gtk.Template.Child()
    restore_session_switch = Gtk.Template.Child()

    automatic_reload_switch = Gtk.Template.Child()

    preferences_dialog = Gtk.Template.Child()
    preferences_button = Gtk.Template.Child()
    theme_toggle_button = Gtk.Template.Child()
    home_button_headerbar = Gtk.Template.Child()

    points_group = Gtk.Template.Child()
    spheres_switch = Gtk.Template.Child()
    points_size_spin = Gtk.Template.Child()
    point_sprites_type_combo = Gtk.Template.Child()
    sprite_size_spin = Gtk.Template.Child()

    material_group = Gtk.Template.Child()

    model_roughness_spin = Gtk.Template.Child()
    model_metallic_spin = Gtk.Template.Child()
    model_color_button = Gtk.Template.Child()
    model_opacity_spin = Gtk.Template.Child()

    armature_switch = Gtk.Template.Child()
    checkerboard_switch = Gtk.Template.Child()
    normal_glyphs_switch = Gtk.Template.Child()
    normal_glyphs_scale_spin = Gtk.Template.Child()
    display_depth_switch = Gtk.Template.Child()
    skin_weights_switch = Gtk.Template.Child()
    skin_weights_mode_combo = Gtk.Template.Child()
    skin_weights_joint_combo = Gtk.Template.Child()
    stats_overlay_switch = Gtk.Template.Child()

    model_color_row = Gtk.Template.Child()
    model_scivis_component_combo = Gtk.Template.Child()
    color_group = Gtk.Template.Child()

    startup_stack = Gtk.Template.Child()

    settings_section = Gtk.Template.Child()

    save_dialog = Gtk.Template.Child()
    settings_column_view = Gtk.Template.Child()
    settings_column_view_name_column = Gtk.Template.Child()
    settings_column_view_value_column = Gtk.Template.Child()
    save_settings_button = Gtk.Template.Child()
    save_settings_name_entry = Gtk.Template.Child()
    save_settings_extensions_entry = Gtk.Template.Child()
    save_settings_expander = Gtk.Template.Child()

    animation_group = Gtk.Template.Child()
    animation_combo = Gtk.Template.Child()
    animation_time_adj = Gtk.Template.Child()
    animation_time_scale = Gtk.Template.Child()
    play_button = Gtk.Template.Child()

    object_tree_button = Gtk.Template.Child()
    object_tree_popover = Gtk.Template.Child()
    object_tree_view = Gtk.Template.Child()

    width = 600
    height = 600
    distance = 0

    no_file_loaded = True

    def __init__(self, application=None, startup_filepath=None):
        super().__init__(application=application)

        self.logger = logger_lib.logger

        # Flags
        self.applying_breakpoint = False
        self.block_reload = True
        self._anim_bindings = []
        self._playing_handler_id = 0
        self._switching_tab = False
        self._pending_open_paths: list[str] = []
        self._mesh_stats = None
        self._armature_xray_restore = None
        self._depth_opacity_restore = None
        self._skin_weights_scivis_restore = None
        self._skin_weights_base_path = None
        self._skin_weights_heat_temp = None
        self._skin_weights_joints = []
        self.filepath = ""
        self.file_name = ""
        self._cached_time_stamp = 0.0

        # Settings
        self.window_settings = WindowSettings()
        self.saved_settings = Gio.Settings.new('io.github.nokse22.Exhibit')

        builder = Gtk.Builder.new_from_resource(_HELP_OVERLAY_RESOURCE)
        self.set_help_overlay(builder.get_object("help_overlay"))

        self._setup_window_actions()

        # Initialize the change checker
        self.change_checker = PeriodicChecker(
            self.periodic_check_for_file_change)

        # Saving all the useful paths
        data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share", "exhibit"
        )

        self.hdri_path = os.path.join(data_home, "HDRIs") + "/"
        self.hdri_thumbnails_path = self.hdri_path + "thumbnails/"

        self.user_configurations_path = os.path.join(
            data_home, "configurations"
        ) + "/"
        # Alias used by the app action open-configs-folder.
        self.configs_path = self.user_configurations_path

        os.makedirs(self.user_configurations_path, exist_ok=True)
        os.makedirs(os.path.join(data_home, "other files"), exist_ok=True)

        # Create the hdri folder and add the default if there are none
        self.setup_hdri_folder()

        # Loading the saved configurations
        self.setup_configurations()

        # Setting drop target type
        self.view_drop_target.set_gtypes([Gdk.FileList])
        self.loading_drop_target.set_gtypes([Gdk.FileList])
        self._refresh_recent_files_ui()

        # Setting the window to the last state
        self.set_default_size(
            self.saved_settings.get_int("startup-width"),
            self.saved_settings.get_int("startup-height")
        )
        self.split_view.set_show_sidebar(
            self.saved_settings.get_boolean("startup-sidebar-show"))
        self.window_settings.set_setting(
            "sidebar-show",
            self.saved_settings.get_boolean("startup-sidebar-show"))

        # Getting the saved HDRI and generating thumbnails
        self.hdri_file_row.file_patterns = image_patterns
        self.hdri_file_row.window = self

        for filename in list_files(self.hdri_path):
            name, _ext = os.path.splitext(filename)

            thumbnail = self.hdri_thumbnails_path + name + ".jpeg"
            filepath = self.hdri_path + filename
            try:
                if not os.path.isfile(thumbnail):
                    thumbnail = self.generate_thumbnail(filepath)
                self.hdri_file_row.add_suggested_file(thumbnail, filepath)
            except Exception:
                self.logger.warning(f"Couldn't open HDRI file {filepath}, skipping")

        # First empty viewer tab (bindings + settings target).
        self._add_viewer_tab(title=_("Untitled"), select=True)
        # close-page is connected in code: signals nested under GtkPaned
        # start-child are not always seen by Gtk.Template.Callback scanning.
        self.tab_view.connect("close-page", self.on_tab_close_page)
        self.tab_view.connect(
            "notify::selected-page", self.on_tab_selected_page)

        if self.window_settings.get_setting("orthographic").value:
            self.f3d_viewer.orthographic = (
                self.window_settings.get_setting("orthographic").value)

        self.style_manager = Adw.StyleManager.get_default()
        self.style_manager.connect(
            "notify::dark", self.update_background_color)

        self.update_background_color()

        # Setting up the save settings dialog
        def _on_factory_setup(_factory, list_item):
            label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
            list_item.set_child(label)

        def _on_factory_bind(_factory, list_item, what):
            label_widget = list_item.get_child()
            setting = list_item.get_item()
            label_widget.set_label(str(getattr(setting, what)))

        self.settings_column_view_name_column.get_factory().connect(
            "setup", _on_factory_setup)
        self.settings_column_view_name_column.get_factory().connect(
            "bind", _on_factory_bind, "name")
        self.settings_column_view_value_column.get_factory().connect(
            "setup", _on_factory_setup)
        self.settings_column_view_value_column.get_factory().connect(
            "bind", _on_factory_bind, "value")

        selection = Gtk.NoSelection.new(model=self.window_settings)
        self.settings_column_view.set_model(model=selection)

        self.save_settings_button.connect(
            "clicked", self.on_save_settings_button_clicked)
        self.save_settings_name_entry.connect(
            "changed", self.on_save_settings_name_entry_changed)
        self.save_settings_extensions_entry.connect(
            "changed", self.on_save_settings_extensions_entry_changed)

        self._wire_settings_widgets()

        self.play_button.connect("clicked", self.on_play_button_clicked)
        self._bind_animation_controls(self.f3d_viewer)

        self._block_animation_combo = False
        self.animation_combo.connect(
            "notify::selected", self.on_animation_combo_changed)

        self._block_object_tree = False
        self._scene_tree_roots: list[ObjectTreeItem] = []
        self._object_tree_check_handlers: dict[int, int] = {}
        self._setup_object_tree_view()

        self.block_reload = True

        # Sync the UI with the settings (batched → one viewer options update)
        self.window_settings.sync_all_settings()
        self._update_all_viewers_options(self.window_settings.get_view_settings())

        self.block_reload = False
        self._update_tab_bar_visibility()

        self.connect("notify::is-active", self.on_window_is_active)

        if startup_filepath:
            self.logger.info(f"startup file detected: {startup_filepath}")
            self.load_file(filepath=startup_filepath)
        else:
            self._restore_session_files()

        GLib.timeout_add(250, self._maybe_restore_split_compare)

        self.logger.info("Started")

    # Functions to set the settings

    # Functions related to the save settings dialog

    def on_tab_close_page(self, tab_view, page):
        return TabsMixin.on_tab_close_page(self, tab_view, page)


    def _setup_window_actions(self) -> None:
        """Register window Gio actions and keyboard accelerators."""
        self.save_as_action = self.create_action(
            'save-as-image', self.open_save_file_chooser)
        self.open_new_action = self.create_action(
            'open-new', self.open_file_chooser)
        self.open_new_action = self.create_action(
            'add-new', self.open_file_chooser)
        self.create_action('open-folder', self.open_folder_chooser)

        self.orthographic_action = Gio.SimpleAction.new_stateful(
            "orthographic",
            None,
            GLib.Variant(
                "b", self.window_settings.get_setting("orthographic").value))
        self.orthographic_action.connect(
            "change-state", self.orthographic_state_changed)
        self.window_settings.get_setting("orthographic").connect(
            "changed", self.on_orthographic_changed)
        self.add_action(self.orthographic_action)

        # Compare: keep peer-tab cameras matched to the active view.
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
        self.split_compare_pin_check.connect(
            "notify::active", self._on_split_compare_pin_toggled
        )
        if self.split_compare_main_paned is not None:
            self.split_compare_main_paned.connect(
                "notify::position", self._on_split_compare_sash_changed
            )

        app = self.get_application()
        if app is not None:
            app.set_accels_for_action(
                "win.sync-cameras", ["<Primary><Shift>c"]
            )
            app.set_accels_for_action(
                "win.open-new", ["<Primary>o"]
            )
            app.set_accels_for_action(
                "win.open-folder", ["<Primary><Shift>o"]
            )
            app.set_accels_for_action(
                "win.split-compare", ["<Primary><Shift>d"]
            )
            app.set_accels_for_action(
                "win.split-compare-swap", ["<Primary><Shift>x"]
            )

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
        self.save_settings_action.set_enabled(False)
        self._init_preferences_actions()
        self._init_home_button()

    def _wire_settings_widgets(self) -> None:
        """Connect sidebar settings widgets to WindowSettings."""
        self.window_settings.connect(
            "changed-other", self.on_other_setting_changed)
        self.window_settings.connect(
            "changed-internal", self.on_internal_setting_changed)
        self.window_settings.connect(
            "changed-view", self.on_view_setting_changed)

        switches = [
            (self.grid_switch, "grid"),
            (self.absolute_grid_switch, "grid-absolute"),
            (self.translucency_switch, "translucency-support"),
            (self.tone_mapping_switch, "tone-mapping"),
            (self.ambient_occlusion_switch, "ambient-occlusion"),
            (self.anti_aliasing_switch, "anti-aliasing"),
            (self.hdri_ambient_switch, "hdri-ambient"),
            (self.edges_switch, "show-edges"),
            (self.spheres_switch, "sprite-enabled"),
            (self.use_skybox_switch, "hdri-skybox"),
            (self.blur_switch, "blur-background"),
            (self.use_color_switch, "use-color"),
            (self.automatic_settings_switch, "auto-best"),
            (self.automatic_reload_switch, "auto-reload"),
            (self.point_up_switch, "point-up"),
            (self.nav_invert_y_switch, "nav-invert-y"),
            (self.nav_invert_x_switch, "nav-invert-x"),
            (self.nav_zoom_to_cursor_switch, "nav-zoom-to-cursor"),
            (self.nav_orbit_around_cursor_switch, "nav-orbit-around-cursor"),
            (self.nav_touchpad_orbit_switch, "nav-touchpad-orbit"),
            (self.nav_mmb_click_pivot_switch, "nav-mmb-click-pivot"),
            (self.armature_switch, "armature-enable"),
            (self.checkerboard_switch, "checkerboard-enable"),
            (self.normal_glyphs_switch, "normal-glyphs"),
            (self.display_depth_switch, "display-depth"),
            (self.skin_weights_switch, "skin-weights"),
            (self.stats_overlay_switch, "stats-overlay"),
        ]

        for switch, name in switches:
            switch.connect("notify::active", self.on_switch_toggled, name)
            setting = self.window_settings.get_setting(name)
            setting.connect("changed", self.set_switch_to, switch)

        spins = [
            (self.edges_width_spin, "edges-width"),
            (self.points_size_spin, "point-size"),
            (self.sprite_size_spin, "sprites-size"),
            (self.model_roughness_spin, "model-roughness"),
            (self.model_metallic_spin, "model-metallic"),
            (self.model_opacity_spin, "model-opacity"),
            (self.normal_glyphs_scale_spin, "normal-glyphs-scale"),
            (self.blur_coc_spin, "blur-coc"),
            (self.light_intensity_spin, "light-intensity"),
            (self.nav_orbit_sensitivity_spin, "nav-orbit-sensitivity"),
            (self.nav_zoom_sensitivity_spin, "nav-zoom-sensitivity"),
            (self.nav_pan_sensitivity_spin, "nav-pan-sensitivity"),
        ]

        for spin, name in spins:
            spin.connect("notify::value", self.on_spin_changed, name)
            setting = self.window_settings.get_setting(name)
            setting.connect("changed", self.set_spin_to, spin)

        self.model_color_button.connect(
            "notify::rgba", self.on_color_changed, "model-color")
        self.background_color_button.connect(
            "notify::rgba", self.on_color_changed, "bg-color")
        self.window_settings.get_setting("model-color").connect(
            "changed", self.set_color_button, self.model_color_button)
        self.window_settings.get_setting("bg-color").connect(
            "changed", self.set_color_button, self.background_color_button)

        self.hdri_file_row.connect(
            "delete-file", self.on_delete_skybox)
        self.hdri_file_row.connect(
            "file-added", lambda row, filepath: self.load_hdri(filepath))
        self.window_settings.get_setting("hdri-file").connect(
            "changed", self.set_hdri_file_row)

        self.model_scivis_component_combo.connect(
            "notify::selected", self.on_scivis_component_combo_changed)
        self.window_settings.get_setting("up").connect(
            "changed", self.set_up_direction_combo)
        self.window_settings.get_setting("scivis-component").connect(
            "changed", self.set_scivis_component_combo)
        self.window_settings.get_setting("cells").connect(
            "changed", self.set_scivis_component_combo)
        self.point_sprites_type_combo.connect(
            "notify::selected", self.point_sprites_type_combo_changed)
        self.window_settings.get_setting("sprites-type").connect(
            "changed", self.set_point_sprites_type_combo_changed)

        self.skin_weights_mode_combo.connect(
            "notify::selected", self.on_skin_weights_mode_combo_changed)
        self.skin_weights_joint_combo.connect(
            "notify::selected", self.on_skin_weights_joint_combo_changed)
        self.window_settings.get_setting("skin-weights-mode").connect(
            "changed", self.set_skin_weights_mode_combo)
        self.window_settings.get_setting("skin-weights").connect(
            "changed", lambda *_: self._refresh_skin_weights_joint_combo())

        self.background_color_button.connect(
            "notify::rgba", self.update_background_color)

        self.up_direction_combo.connect(
            "notify::selected", self.on_up_direction_combo_changed)

        self.window_settings.set_setting(
            "auto-best", self.saved_settings.get_boolean("auto-best"))

        self.saved_settings.bind(
            "restore-session",
            self.restore_session_switch,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )
        self.restore_session_switch.connect(
            "notify::active", self.on_restore_session_toggled)

        self._load_nav_settings_from_gschema()
        # Push defaults into switch/spin widgets without fighting gschema bind.
        for key in (
            "nav-invert-x",
            "nav-invert-y",
            "nav-zoom-to-cursor",
            "nav-orbit-around-cursor",
            "nav-touchpad-orbit",
            "nav-mmb-click-pivot",
            "nav-orbit-sensitivity",
            "nav-zoom-sensitivity",
            "nav-pan-sensitivity",
            "point-up",
        ):
            setting = self.window_settings.get_setting(key)
            setting.emit("changed", setting.name, setting.type)
        self._sync_theme_toggle_button()

    def create_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        return action



def list_files(directory):
    items = os.listdir(directory)
    files = [
        item for item in items if os.path.isfile(os.path.join(directory, item))
    ]
    return files
