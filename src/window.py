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

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Gdk, Gio, GLib, GObject, Pango
from .widgets import FileRow, ViewerTab
from wand.image import Image

from . import logger_lib
from .settings_manager import WindowSettings
from .meshopt_decompress import MeshoptError, cleanup_decompressed, prepare_glb_for_load
from .gltf_scene_graph import SceneTreeNode, glb_has_skins, tree_has_mesh
from .mesh_stats import MeshStats, collect_mesh_stats, format_overlay_text

import f3d

from gettext import gettext as _

_HELP_OVERLAY_RESOURCE = "/io/github/nokse22/Exhibit/gtk/help-overlay.ui"


class ObjectTreeItem(GObject.Object):
    """GObject wrapper for a glTF scene node in the floating object tree."""

    __gtype_name__ = "ExhibitObjectTreeItem"

    def __init__(self, node: SceneTreeNode):
        super().__init__()
        self.index = int(node.index)
        self.name = node.name
        self.has_mesh = bool(node.has_mesh)
        self.children = [ObjectTreeItem(child) for child in node.children]


up_dir_n_to_string = {
    0: "-X",
    1: "+X",
    2: "-Y",
    3: "+Y",
    4: "-Z",
    5: "+Z"
}

up_dir_string_to_n = {
    "-X": 0,
    "+X": 1,
    "-Y": 2,
    "+Y": 3,
    "-Z": 4,
    "+Z": 5
}

up_dirs_vector = {
    "-X": (-1.0, 0.0, 0.0),
    "+X": (1.0, 0.0, 0.0),
    "-Y": (0.0, -1.0, 0.0),
    "+Y": (0.0, 1.0, 0.0),
    "-Z": (0.0, 0.0, -1.0),
    "+Z": (0.0, 0.0, 1.0)
}

allowed_extensions = []

for reader in f3d.Engine.get_readers_info():
    # print(f"Reader: {reader.name}\nDescr: {reader.description}\nExt: {reader.extensions}\nMime: {reader.mime_types}\np name: {reader.plugin_name}\nscene: {reader.has_scene_reader}\ngeom: {reader.has_geometry_reader}\n\n")
    # print(reader.has_scene_reader)
    allowed_extensions += reader.extensions

print(allowed_extensions)

image_patterns = ["hdr", "exr", "png", "jpg", "pnm", "tiff", "bmp"]


class PeriodicChecker(GObject.Object):
    def __init__(self, function):
        super().__init__()

        self._running = False
        self._function = function

    def run(self):
        if self._running:
            return
        self._running = True
        GLib.timeout_add(500, self.periodic_check)

    def stop(self):
        self._running = False

    def periodic_check(self):
        if self._running:
            self._function()
            return True
        else:
            return False


@Gtk.Template(resource_path='/io/github/nokse22/Exhibit/ui/window.ui')
class Viewer3dWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'Viewer3dWindow'

    loading_label = Gtk.Template.Child()

    split_view = Gtk.Template.Child()

    title_widget = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    toolbar_view = Gtk.Template.Child()
    tab_view = Gtk.Template.Child()
    tab_bar = Gtk.Template.Child()

    view_drop_target = Gtk.Template.Child()
    loading_drop_target = Gtk.Template.Child()

    toast_overlay = Gtk.Template.Child()

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

    automatic_settings_switch = Gtk.Template.Child()

    automatic_reload_switch = Gtk.Template.Child()

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
    play_button = Gtk.Template.Child()

    object_tree_button = Gtk.Template.Child()
    object_tree_popover = Gtk.Template.Child()
    object_tree_view = Gtk.Template.Child()

    width = 600
    height = 600
    distance = 0

    no_file_loaded = True

    _cached_time_stamp = 0

    def __init__(self, application=None, startup_filepath=None):
        super().__init__(application=application)

        self.logger = logger_lib.logger

        # Flags
        self.applying_breakpoint = False
        self.block_reload = True
        self._anim_bindings = []
        self._playing_handler_id = 0
        self._switching_tab = False
        self._mesh_stats = None
        self._armature_xray_restore = None
        self.filepath = ""
        self.file_name = ""

        # Settings
        self.window_settings = WindowSettings()
        self.saved_settings = Gio.Settings.new('io.github.nokse22.Exhibit')

        builder = Gtk.Builder.new_from_resource(_HELP_OVERLAY_RESOURCE)
        self.set_help_overlay(builder.get_object("help_overlay"))

        # Defining all the actions
        self.save_as_action = self.create_action(
            'save-as-image', self.open_save_file_chooser)
        self.open_new_action = self.create_action(
            'open-new', self.open_file_chooser)
        self.open_new_action = self.create_action(
            'add-new', self.open_file_chooser)

        self.orthographic_action = Gio.SimpleAction.new_stateful(
            "orthographic",
            None,
            GLib.Variant(
                "b", self.window_settings.get_setting("orthographic")))
        self.orthographic_action.connect(
            "change-state", self.orthographic_state_changed)
        self.window_settings.get_setting("orthographic").connect(
            "changed", self.on_orthographic_changed)
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
        self.save_settings_action.set_enabled(False)

        # Initialize the change checker
        self.change_checker = PeriodicChecker(
            self.periodic_check_for_file_change)

        # Saving all the useful paths
        data_home = os.environ["XDG_DATA_HOME"]

        self.hdri_path = data_home + "/HDRIs/"
        self.hdri_thumbnails_path = self.hdri_path + "/thumbnails/"

        self.user_configurations_path = data_home + "/configurations/"

        os.makedirs(self.user_configurations_path, exist_ok=True)
        os.makedirs(data_home + "/other files/", exist_ok=True)

        # Create the hdri folder and add the default if there are none
        self.setup_hdri_folder()

        # Loading the saved configurations
        self.setup_configurations()

        # Setting drop target type
        self.view_drop_target.set_gtypes([Gdk.FileList])
        self.loading_drop_target.set_gtypes([Gdk.FileList])

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

        # Setting the UI and connecting widgets
        self.window_settings.connect(
            "changed-other", self.on_other_setting_changed)
        self.window_settings.connect(
            "changed-internal", self.on_internal_setting_changed)
        self.window_settings.connect(
            "changed-view", self.on_view_setting_changed)

        # Switches signals
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
            (self.armature_switch, "armature-enable"),
            (self.stats_overlay_switch, "stats-overlay"),
        ]

        for switch, name in switches:
            switch.connect("notify::active", self.on_switch_toggled, name)
            setting = self.window_settings.get_setting(name)
            setting.connect("changed", self.set_switch_to, switch)

        # Spins
        spins = [
            (self.edges_width_spin, "edges-width"),
            (self.points_size_spin, "point-size"),
            (self.sprite_size_spin, "sprites-size"),
            (self.model_roughness_spin, "model-roughness"),
            (self.model_metallic_spin, "model-metallic"),
            (self.model_opacity_spin, "model-opacity"),
            (self.blur_coc_spin, "blur-coc"),
            (self.light_intensity_spin, "light-intensity"),
        ]

        for spin, name in spins:
            spin.connect("notify::value", self.on_spin_changed, name)
            setting = self.window_settings.get_setting(name)
            setting.connect("changed", self.set_spin_to, spin)

        # Color buttons
        self.model_color_button.connect(
            "notify::rgba", self.on_color_changed, "model-color")
        self.background_color_button.connect(
            "notify::rgba", self.on_color_changed, "bg-color")
        self.window_settings.get_setting("model-color").connect(
            "changed", self.set_color_button, self.model_color_button)
        self.window_settings.get_setting("bg-color").connect(
            "changed", self.set_color_button, self.background_color_button)

        # File rows
        self.hdri_file_row.connect(
            "delete-file", self.on_delete_skybox)
        self.hdri_file_row.connect(
            "file-added", lambda row, filepath: self.load_hdri(filepath))
        self.window_settings.get_setting("hdri-file").connect(
            "changed", self.set_hdri_file_row)

        # Combos
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

        # Others
        self.background_color_button.connect(
            "notify::rgba", self.update_background_color)

        self.up_direction_combo.connect(
            "notify::selected", self.on_up_direction_combo_changed)

        self.window_settings.set_setting(
            "auto-best", self.saved_settings.get_boolean("auto-best"))

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

        if startup_filepath:
            self.logger.info(f"startup file detected: {startup_filepath}")
            self.load_file(filepath=startup_filepath)

        self.logger.info("Started")

    # ---- Multi-document tabs ---------------------------------------------

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
        title = tab.file_name or _("Untitled")
        page.set_title(title)
        page.set_icon(Gio.ThemedIcon.new("image-x-generic-symbolic"))
        tooltip = tab.filepath or title
        if hasattr(page, "set_tooltip"):
            page.set_tooltip(tooltip)
        else:
            tab.set_tooltip_text(tooltip)

    def _add_viewer_tab(self, title: str = "", select: bool = True) -> ViewerTab:
        tab = ViewerTab()
        if title:
            tab.file_name = title
        page = self.tab_view.append(tab)
        self._configure_tab_page(page, tab)
        tab.viewer.update_options(self.window_settings.get_view_settings())
        if select:
            self.tab_view.set_selected_page(page)
            self._bind_animation_controls(tab.viewer)
        self._update_tab_bar_visibility()
        return tab

    def _bind_animation_controls(self, viewer):
        for binding in self._anim_bindings:
            binding.unbind()
        flags_range = GObject.BindingFlags.BIDIRECTIONAL
        flags_value = (
            GObject.BindingFlags.BIDIRECTIONAL
            | GObject.BindingFlags.SYNC_CREATE)
        self._anim_bindings = [
            self.animation_time_adj.bind_property(
                "lower", viewer, "lower-time-range", flags_range),
            self.animation_time_adj.bind_property(
                "upper", viewer, "upper-time-range", flags_range),
            self.animation_time_adj.bind_property(
                "value", viewer, "animation-time", flags_value),
        ]
        if self._playing_handler_id:
            # Disconnect from previous viewer if still alive.
            try:
                for tab in self._iter_tabs():
                    if tab.viewer.handler_is_connected(self._playing_handler_id):
                        tab.viewer.disconnect(self._playing_handler_id)
                        break
            except Exception:
                pass
        self._playing_handler_id = viewer.connect(
            "notify::playing", self.on_playing_changed)
        self.on_playing_changed()

    def _sync_window_from_tab(self, tab: ViewerTab | None):
        if tab is None:
            self.filepath = ""
            self.file_name = ""
            self._mesh_stats = None
            return
        self.filepath = tab.filepath
        self.file_name = tab.file_name
        self._mesh_stats = tab.mesh_stats
        self._armature_xray_restore = tab.armature_xray_restore
        if tab.loaded:
            self.set_title(_("Exhibit - {}").format(tab.file_name or _("Untitled")))
            self.title_widget.set_subtitle(tab.file_name)
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
                self.update_time_stamp()
                if self.window_settings.get_setting("auto-reload").value:
                    self.change_checker.run()
                tab.viewer.grab_focus()
                # Ensure GL picks up the visible allocation after a switch.
                GLib.idle_add(tab.viewer.queue_render)
            self._update_tab_bar_visibility()
        finally:
            self._switching_tab = False

    @Gtk.Template.Callback("on_tab_close_page")
    def on_tab_close_page(self, tab_view, page):
        tab = page.get_child()
        self.tab_view.close_page_finish(page, True)
        if isinstance(tab, ViewerTab):
            try:
                tab.viewer.set_auto_render(False)
            except Exception:
                pass
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
            self._switching_tab = True
            try:
                self._add_viewer_tab(select=True)
            finally:
                self._switching_tab = False
        else:
            self.on_tab_selected_page()
        self._update_tab_bar_visibility()
        return Gdk.EVENT_STOP

    def setup_configurations(self):
        self.configurations = Gio.resources_lookup_data(
            '/io/github/nokse22/Exhibit/configurations.json',
            Gio.ResourceLookupFlags.NONE).get_data().decode('utf-8')
        self.configurations = json.loads(self.configurations)

        for filename in os.listdir(self.user_configurations_path):
            if filename.endswith('.json'):
                filepath = os.path.join(
                    self.user_configurations_path, filename)
                with open(filepath, 'r') as file:
                    try:
                        configuration = json.load(file)

                        # Check if the loaded configurations
                        #   has all the required keys
                        required_keys = {
                            "name", "formats",
                            "view-settings", "other-settings"
                        }
                        first_key_value = next(iter(configuration.values()))
                        if required_keys.issubset(first_key_value.keys()):
                            self.configurations.update(configuration)
                        else:
                            self.logger.error(
                                f"Error: {filepath} is missing required keys.")

                    except json.JSONDecodeError as e:
                        self.logger.error(f"Error reading {filename}: {e}")

        item = Gio.MenuItem.new("Custom", "win.settings")
        item.set_attribute_value("target", GLib.Variant.new_string("custom"))
        self.settings_section.append_item(item)

        for key, setting in self.configurations.items():
            item = Gio.MenuItem.new(setting["name"], "win.settings")
            item.set_attribute_value("target", GLib.Variant.new_string(key))
            self.settings_section.append_item(item)

    def setup_hdri_folder(self):
        if os.path.isdir(self.hdri_path):
            return

        os.makedirs(self.hdri_path, exist_ok=True)
        os.makedirs(self.hdri_thumbnails_path, exist_ok=True)

        hdri_names = ["city.hdr", "meadow.hdr", "field.hdr", "sky.hdr"]
        for hdri_filename in hdri_names:
            if not os.path.isfile(self.hdri_path + hdri_filename):
                hdri = Gio.resources_lookup_data(
                    '/io/github/nokse22/Exhibit/HDRIs/' + hdri_filename,
                    Gio.ResourceLookupFlags.NONE).get_data()
                hdri_bytes = bytearray(hdri)
                with open(self.hdri_path + hdri_filename, 'wb') as output_file:
                    output_file.write(hdri_bytes)
                self.logger.info(f"Added {hdri_filename}")

    #
    # Functions that set the UI from the settings, triggered when
    #   a setting has changed.

    def set_hdri_file_row(self, setting, name, enum):
        self.logger.info(f"Setting hdri file row filename to {setting.value}")
        self.hdri_file_row.set_filename(setting.value)

    def set_switch_to(self, setting, name, enum, switch):
        self.logger.info(f"Setting switch to {setting.value}")
        switch.set_active(setting.value)

    def set_spin_to(self, setting, name, enum, spin):
        self.logger.info(f"Setting spin to {setting.value}")
        spin.set_value(setting.value)

    def set_up_direction_combo(self, *args):
        val = up_dir_string_to_n[self.window_settings.get_setting("up").value]
        self.logger.info(f"Setting up direction combo to {val}")
        self.up_direction_combo.set_selected(val)

    def set_color_button(self, setting, name, enum, color_button):
        rgba = Gdk.RGBA()
        rgba.parse(list_to_rgb(setting.value))
        color_button.set_rgba(rgba)

    def set_scivis_component_combo(self, setting, *args):
        selected = self.model_scivis_component_combo.get_selected()
        self.logger.debug(
            f"Setting scivis component combo, selected: {selected}")
        self.model_color_row.set_sensitive(True if selected == 0 else False)

        if (self.window_settings.get_setting("scivis-component").value == -1 and
                self.window_settings.get_setting("cells").value):
            self.model_scivis_component_combo.set_selected(0)
        else:
            self.model_scivis_component_combo.set_selected(
                -self.window_settings.get_setting("scivis-component").value + 1)

    def set_point_sprites_type_combo_changed(self, setting, *args):
        if self.window_settings.get_setting("scivis-component").value == "spheres":
            self.point_sprites_type_combo.set_selected(0)
        else:
            self.point_sprites_type_combo.set_selected(1)

    # Functions that are called when a UI changes, they should only
    #   set the corresponding setting.

    def _animation_index_from_combo(self):
        selected = self.animation_combo.get_selected()
        if selected == Gtk.INVALID_LIST_POSITION:
            return 0
        # First item is "All animations" → -1
        if selected == 0:
            return -1
        return int(selected) - 1

    def _combo_position_for_animation_index(self, index):
        if index < 0:
            return 0
        return int(index) + 1

    def refresh_animation_combo(self):
        count = self.f3d_viewer.available_animations()
        if count <= 0:
            self.animation_group.set_visible(False)
            return

        names = self.f3d_viewer.get_animation_names()
        string_list = Gtk.StringList()
        string_list.append(_("All animations"))
        for i in range(count):
            name = names[i] if i < len(names) else ""
            if name:
                string_list.append(name)
            else:
                string_list.append(_("Animation {}").format(i))

        current = self.window_settings.get_setting("animation-index").value
        if current >= count:
            current = 0
            self.window_settings.set_setting("animation-index", current, False)

        position = self._combo_position_for_animation_index(current)
        if position >= string_list.get_n_items():
            position = 1 if count > 0 else 0

        self._block_animation_combo = True
        try:
            self.animation_combo.set_model(string_list)
            self.animation_combo.set_selected(position)
        finally:
            self._block_animation_combo = False

        self.animation_group.set_visible(True)

    def on_animation_combo_changed(self, *args):
        if self._block_animation_combo:
            return

        index = self._animation_index_from_combo()
        self.window_settings.set_setting("animation-index", index)
        self.f3d_viewer.update_options({"animation-index": index})
        self.f3d_viewer.playing = False
        # F3D switches clip via scene.animation.indices — no file reload.
        lower = self.f3d_viewer.lower_time_range
        upper = self.f3d_viewer.upper_time_range
        self.animation_time_adj.set_lower(lower)
        self.animation_time_adj.set_upper(upper)
        self.f3d_viewer.notify("lower-time-range")
        self.f3d_viewer.notify("upper-time-range")
        self.f3d_viewer.animation_time = lower

    def _setup_object_tree_view(self):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_object_tree_setup)
        factory.connect("bind", self._on_object_tree_bind)
        factory.connect("unbind", self._on_object_tree_unbind)
        self.object_tree_view.set_factory(factory)
        empty = Gio.ListStore.new(ObjectTreeItem)
        self.object_tree_view.set_model(Gtk.NoSelection.new(empty))

    def _object_tree_child_model(self, item):
        if not isinstance(item, ObjectTreeItem) or not item.children:
            return None
        store = Gio.ListStore.new(ObjectTreeItem)
        for child in item.children:
            store.append(child)
        return store

    def refresh_object_tree(self):
        try:
            roots = self.f3d_viewer.get_scene_tree()
            available = tree_has_mesh(roots)
            self.object_tree_button.set_visible(available)

            if not available:
                self._scene_tree_roots = []
                empty = Gio.ListStore.new(ObjectTreeItem)
                self.object_tree_view.set_model(Gtk.NoSelection.new(empty))
                if self.object_tree_popover is not None and self.object_tree_popover.get_visible():
                    self.object_tree_popover.popdown()
                return

            self._scene_tree_roots = [ObjectTreeItem(node) for node in roots]
            root_store = Gio.ListStore.new(ObjectTreeItem)
            for item in self._scene_tree_roots:
                root_store.append(item)

            tree_model = Gtk.TreeListModel.new(
                root_store,
                False,
                True,
                self._object_tree_child_model,
            )
            self.object_tree_view.set_model(Gtk.NoSelection.new(tree_model))
        except Exception as e:
            self.logger.error(f"Error while building object tree: {e}")
            self.object_tree_button.set_visible(False)

    def _on_object_tree_setup(self, factory, list_item):
        expander = Gtk.TreeExpander()
        expander.set_indent_for_icon(True)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        check = Gtk.CheckButton()
        label = Gtk.Label(xalign=0.0, hexpand=True)
        label.set_wrap(False)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(check)
        row.append(label)
        expander.set_child(row)
        list_item.set_child(expander)

    def _on_object_tree_bind(self, factory, list_item):
        tree_row = list_item.get_item()
        if tree_row is None:
            return
        item = tree_row.get_item()
        expander = list_item.get_child()
        expander.set_list_row(tree_row)

        row = expander.get_child()
        check = row.get_first_child()
        label = check.get_next_sibling()
        label.set_label(item.name)
        if item.has_mesh:
            label.remove_css_class("object-tree-structural")
        else:
            label.add_css_class("object-tree-structural")

        hidden = self.f3d_viewer.get_hidden_part_indices()
        self._block_object_tree = True
        try:
            check.set_active(item.index not in hidden)
        finally:
            self._block_object_tree = False

        handler_id = check.connect(
            "notify::active", self.on_object_part_toggled, item.index
        )
        self._object_tree_check_handlers[id(check)] = handler_id

    def _on_object_tree_unbind(self, factory, list_item):
        expander = list_item.get_child()
        if expander is None:
            return
        row = expander.get_child()
        if row is None:
            return
        check = row.get_first_child()
        handler_id = self._object_tree_check_handlers.pop(id(check), None)
        if handler_id is not None:
            check.disconnect(handler_id)

    def on_object_part_toggled(self, check, _pspec, node_index):
        if self._block_object_tree:
            return
        if not self.f3d_viewer.set_part_visible(node_index, check.get_active()):
            self.send_toast(_("Couldn't update object visibility"))
            self._block_object_tree = True
            try:
                check.set_active(not check.get_active())
            finally:
                self._block_object_tree = False

    def on_switch_toggled(self, switch, active, name):
        self.window_settings.set_setting(name, switch.get_active())

    def on_spin_changed(self, spin, value, name):
        val = float(round(spin.get_value(), 2))
        self.window_settings.set_setting(name, val)

    def on_color_changed(self, btn, color, setting):
        color_list = rgb_to_list(btn.get_rgba().to_string())
        self.window_settings.set_setting(setting, color_list)

    def on_up_direction_combo_changed(self, combo, *args):
        direction = up_dir_n_to_string[combo.get_selected()]
        self.window_settings.set_setting("up", direction)

    def on_scivis_component_combo_changed(self, *args):
        selected = self.model_scivis_component_combo.get_selected()
        self.model_color_row.set_sensitive(True if selected == 0 else False)

        if selected == 0:
            self.window_settings.set_setting("scivis-component", -1, False)
            self.window_settings.set_setting("cells", True)
            self.window_settings.set_setting("scivis-enabled", False)
        else:
            self.window_settings.set_setting("scivis-component", -(selected - 1))
            self.window_settings.set_setting("cells", False)
            self.window_settings.set_setting("scivis-enabled", True)

    def point_sprites_type_combo_changed(self, *args):
        selected = self.point_sprites_type_combo.get_selected()

        if selected == 0:
            self.window_settings.set_setting("sprites-type", "sphere", False)
        else:
            self.window_settings.set_setting("sprites-type", "gaussian", False)
    #
    # Special functions called when a setting changes that trigger
    #   an action like reloading.

    def reload_file(self, pres_or=False):
        if not self.block_reload:
            self.logger.info("Reloading file")
            self.load_file(
                filepath=self.filepath,
                override=True,
                preserve_orientation=pres_or,
                new_tab=False)

    def update_background_color(self, *args):
        self.logger.info(
            f"Use color is: {self.window_settings.get_setting('use-color').value}")
        if self.window_settings.get_setting("use-color").value:
            options = {
                "bg-color": self.window_settings.get_setting("bg-color").value,
            }
            self._update_all_viewers_options(options)
            return
        if self.style_manager.get_dark():
            options = {"bg-color": [0.117, 0.117, 0.117]}
        else:
            options = {"bg-color": [1.0, 1.0, 1.0]}
        self._update_all_viewers_options(options)

    # Functions to set the settings

    def on_view_setting_changed(self, window_settings, setting):
        self.logger.info(f"Setting: {setting.name} to {setting.value}")
        if setting.name == "armature-enable":
            self._apply_armature_mode(bool(setting.value))
            self.check_for_options_change()
            return
        if setting.name == "stats-overlay":
            self._apply_stats_overlay(bool(setting.value))
            self.check_for_options_change()
            return

        options = {setting.name: setting.value}
        self._update_all_viewers_options(options)
        self.check_for_options_change()

        if setting.name == "up":
            self.reload_file()

    def _refresh_mesh_stats(self) -> None:
        tab = self._active_tab()
        if tab is None:
            self._mesh_stats = None
            return
        path = tab.viewer.get_prepared_path() or tab.filepath
        if not path or not os.path.isfile(path):
            self._mesh_stats = None
            tab.mesh_stats = None
            return
        prepared = bool(tab.viewer.get_prepared_path())
        try:
            stats = collect_mesh_stats(path, already_prepared=prepared)
        except Exception as exc:
            self.logger.error(f"Failed to collect mesh stats: {exc}")
            stats = None
        self._mesh_stats = stats
        tab.mesh_stats = stats

    def _apply_stats_overlay(self, enabled: bool) -> None:
        """Show/hide the Gtk stats overlay; refresh counts when enabling."""
        if enabled:
            if self._mesh_stats is None:
                self._refresh_mesh_stats()
            if self._mesh_stats is not None:
                self.stats_overlay_label.set_label(
                    format_overlay_text(self._mesh_stats)
                )
            else:
                self.stats_overlay_label.set_label(_("No stats available"))
            self.stats_overlay_label.set_visible(True)
            # Also drive F3D's native metadata + our text via filename_info.
            info = (
                format_overlay_text(self._mesh_stats)
                if self._mesh_stats is not None
                else ""
            )
            if self.f3d_viewer.engine:
                self.f3d_viewer.engine.options.update(
                    {
                        "ui.metadata": True,
                        "ui.filename": True,
                        "ui.filename_info": info,
                        "ui.backdrop.opacity": 0.55,
                    }
                )
                self.f3d_viewer.queue_render()
            return

        self.stats_overlay_label.set_visible(False)
        if self.f3d_viewer.engine:
            self.f3d_viewer.engine.options.update(
                {
                    "ui.metadata": False,
                    "ui.filename": False,
                    "ui.filename_info": "",
                }
            )
            self.f3d_viewer.queue_render()

    def _apply_armature_mode(self, enabled: bool):
        """
        Toggle F3D armature and apply an X-ray presentation.

        F3D draws bones on top, but with default opacity=1 and line_width=1 the
        skeleton is nearly invisible. Match the documented look (thicker lines
        + translucent mesh).
        """
        xray_opacity = 0.35
        min_line_width = 4.0

        if enabled:
            if self._armature_xray_restore is None:
                self._armature_xray_restore = {
                    "model-opacity": float(
                        self.window_settings.get_setting("model-opacity").value
                    ),
                    "edges-width": float(
                        self.window_settings.get_setting("edges-width").value
                    ),
                }
            line_width = max(
                min_line_width, float(self._armature_xray_restore["edges-width"])
            )
            self.window_settings.begin_view_batch()
            try:
                self.window_settings.set_setting("model-opacity", xray_opacity)
                self.window_settings.set_setting("edges-width", line_width)
            finally:
                self.window_settings.end_view_batch()

            self.f3d_viewer.update_options(
                {
                    "armature-enable": True,
                    "model-opacity": xray_opacity,
                    "edges-width": line_width,
                }
            )

            probe = self.f3d_viewer.get_prepared_path() or self.filepath
            has_skins = glb_has_skins(probe) if probe else None
            if has_skins is False:
                self.send_toast(_("No armature found in this model"))
            return

        restore = self._armature_xray_restore or {
            "model-opacity": 1.0,
            "edges-width": 1.0,
        }
        self._armature_xray_restore = None
        self.window_settings.begin_view_batch()
        try:
            self.window_settings.set_setting(
                "model-opacity", restore["model-opacity"]
            )
            self.window_settings.set_setting("edges-width", restore["edges-width"])
        finally:
            self.window_settings.end_view_batch()

        self.f3d_viewer.update_options(
            {
                "armature-enable": False,
                "model-opacity": restore["model-opacity"],
                "edges-width": restore["edges-width"],
            }
        )

    def on_other_setting_changed(self, window_settings, setting):
        self.logger.info(f"Setting: {setting.name} to {setting.value}")
        if setting.name == "use-color":
            self.update_background_color()
        elif setting.name == "point-up":
            if setting.value:
                self.f3d_viewer.set_view_up(
                    up_dirs_vector[
                        self.window_settings.get_setting("up").value])
                self.f3d_viewer.always_point_up = True
            else:
                self.f3d_viewer.always_point_up = False
        elif setting.name == "auto-reload":
            if setting.value:
                self.change_checker.run()
            else:
                self.change_checker.stop()

        self.check_for_options_change()

    def on_internal_setting_changed(self, window_settings, setting):
        self.logger.info(f"Setting: {setting.name} to {setting.value}")
        if setting.name == "auto-best":
            pass
        elif setting.name == "sidebar-show":
            pass

    # Functions related to the save settings dialog

    def on_save_settings_button_clicked(self, btn):
        # Extract view settings, name, and formats
        view_settings = self.window_settings.get_view_settings()
        other_settings = self.window_settings.get_other_settings()
        name = self.save_settings_name_entry.get_text()
        formats = self.save_settings_extensions_entry.get_text()

        # Format the key
        key = name.lower().replace(' ', '_')

        # Construct the dictionary
        settings_dict = {
            key: {
                "name": name,
                "formats": f".*({formats.replace(', ', '|')})",
                "view-settings": view_settings,
                "other-settings": other_settings
            }
        }

        # Save to JSON file
        with open(self.user_configurations_path + key + '.json', 'w') as j_f:
            json.dump(settings_dict, j_f, indent=4)

        # Update configurations and menu UI
        self.configurations.update(settings_dict)
        item = Gio.MenuItem.new(name, "win.settings")
        item.set_attribute_value("target", GLib.Variant.new_string(key))
        self.settings_section.append_item(item)

        self.save_dialog.close()

    def on_save_settings_name_entry_changed(self, entry):
        if entry.get_text_length() != 0:
            self.save_settings_button.set_sensitive(True)
        else:
            self.save_settings_button.set_sensitive(False)

    def on_save_settings_extensions_entry_changed(self, entry):
        extensions_text = entry.get_text()

        if extensions_text == "":
            entry.remove_css_class("error")
            return

        entered_exts = [ext.strip() for ext in extensions_text.split(',')]

        if all(ext in allowed_extensions for ext in entered_exts):
            entry.remove_css_class("error")
        else:
            entry.add_css_class("error")

    def on_save_settings(self, *args):
        self.save_settings_name_entry.set_text("")
        self.save_settings_extensions_entry.set_text("")
        self.save_settings_expander.set_expanded(False)
        self.save_dialog.present(self)

    def set_settings_from_name(self, name):
        self.logger.debug("settings from name")
        if name == "custom":
            return

        # Get the default settings and change the ones defined by the chosen presets
        options = self.window_settings.get_default_user_customizable_settings()
        for key, value in self.configurations[name]["view-settings"].items():
            options[key] = value

        # Batch view emits so presets do one update_options + one queue_render
        self.window_settings.begin_view_batch()
        for tab in self._iter_tabs():
            tab.viewer.begin_options_batch()
        try:
            for key, value in options.items():
                self.window_settings.set_setting(key, value)
            self._update_all_viewers_options(options, queue_render=False)
            for key, value in self.configurations[name]["other-settings"].items():
                self.window_settings.set_setting(key, value)
        finally:
            self.window_settings.end_view_batch()
            for tab in self._iter_tabs():
                tab.viewer.end_options_batch()

    def check_for_options_change(self):
        if self.block_reload:
            return

        state_name = self.settings_action.get_state().get_string()
        if state_name == "custom":
            return

        self.logger.debug(f"Checking for changed options from {state_name}")

        state_options = self.window_settings.get_default_user_customizable_settings()

        for key, value in self.configurations[state_name]["view-settings"].items():
            state_options[key] = value

        for key, value in self.configurations[state_name]["other-settings"].items():
            state_options[key] = value

        current_settings = self.window_settings.get_user_customized_settings()
        for key, value in state_options.items():
            if key in current_settings:
                if current_settings[key] != value:
                    self.logger.info(
                        f"current key: {key}'s value is {current_settings[key]} != {value}")
                    self.change_setting_state(GLib.Variant("s", "custom"))
                    return

    def periodic_check_for_file_change(self):
        if self.filepath == "":
            return True

        changed = self.update_time_stamp()
        if changed:
            self.logger.debug("file changed")
            self.load_file(preserve_orientation=True, override=True)

        if self.window_settings.get_setting("auto-reload").value:
            return True
        return False

    def update_time_stamp(self):
        try:
            stamp = os.stat(self.filepath).st_mtime
            if stamp != self._cached_time_stamp:
                self._cached_time_stamp = stamp
                return True
            return False
        except Exception:
            return False

    def change_setting_state(self, state):
        self.logger.debug(f"Requested changing settings to {state}")

        if state.get_string() == "custom":
            self.save_settings_action.set_enabled(True)
            self.settings_action.set_state(state)
            return

        self.set_settings_from_name(state.get_string())

        self.settings_action.set_state(state)

        self.save_settings_action.set_enabled(False)

        self.update_background_color()

    def get_gimble_limit(self):
        return self.distance / 10

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

    def on_open_files_response(self, dialog, response):
        try:
            files = dialog.open_multiple_finish(response)
        except Exception as e:
            self.logger.error(f"Exception Opening file: {e}")
            return

        if not files:
            return
        for i in range(files.get_n_items()):
            file = files.get_item(i)
            filepath = file.get_path() if file else None
            if not filepath:
                self.logger.error("Opened file has no local path")
                self.on_file_not_opened(
                    file.get_basename() if file else _("Unknown"))
                continue
            self.logger.info("open file response")
            self.load_file(filepath=filepath)

    def load_file(self, **kwargs):
        filepath = kwargs.get("filepath")
        basename = os.path.basename(filepath or "Nothing")
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
            tab = self._active_tab()
            if tab is None:
                tab = self._add_viewer_tab(title=basename, select=True)
            page = self._tab_page(tab)
            if page is not None:
                page.set_title(basename)
                page.set_loading(True)

        kwargs["_tab"] = tab
        # Extra tabs inherit current preset — skip auto-best churn.
        kwargs["_skip_auto_best"] = bool(new_tab)
        warm = not self.no_file_loaded
        self._update_tab_bar_visibility()

        # Same loading UI for first open and extra tabs.
        self.loading_label.set_label(_("Loading {}").format(basename))
        self.startup_stack.set_visible_child_name("loading_page")
        self.stack.set_visible_child_name("startup_page")

        tab.stats_overlay_label.set_visible(False)
        self.block_reload = True

        if warm:
            # App already up: prepare GLB on a worker while F3D engine inits
            # on the main thread, then scene.add on main (GL-safe + overlap).
            self._start_warm_load(tab, kwargs)
        else:
            tab.viewer.initialize()

            def _start_load(*_args):
                threading.Thread(
                    target=self._load_file, kwargs=kwargs, daemon=True
                ).start()
                return GLib.SOURCE_REMOVE

            GLib.timeout_add(100, _start_load)

    @staticmethod
    def _resolve_readable_path(filepath: str) -> str | None:
        """Return a path the sandbox can read (follow home→/media symlinks)."""
        if not filepath:
            return None
        candidates = [filepath]
        try:
            real = os.path.realpath(filepath)
            if real and real not in candidates:
                candidates.append(real)
        except OSError:
            pass
        for path in candidates:
            try:
                if os.path.isfile(path) and os.access(path, os.R_OK):
                    return path
            except OSError:
                continue
        return None

    def _start_warm_load(self, tab: ViewerTab, kwargs: dict):
        """Overlap GLB prepare (worker) with F3D engine create (main)."""
        filepath = kwargs.get("filepath")
        holder: dict = {}

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
            GLib.idle_add(self._warm_prepare_finished, tab, kwargs, holder)

        threading.Thread(target=prepare_worker, daemon=True).start()
        # Pay for the new tab's engine while prepare runs.
        tab.viewer.initialize()

    def _warm_prepare_finished(self, tab: ViewerTab, kwargs: dict, holder: dict):
        if "err" in holder:
            err = holder["err"]
            path = holder.get("path") or kwargs.get("filepath")
            self.logger.error(f"Warm prepare failed: {err}")
            self.on_file_not_opened(path, tab)
            return GLib.SOURCE_REMOVE

        filepath, load_path, meshopt_temp = holder["ok"]
        viewer = tab.viewer
        if viewer.engine is None:
            viewer.initialize()

        self.change_checker.stop()
        try:
            if not viewer.supports(load_path):
                self.on_file_not_opened(filepath, tab)
                return GLib.SOURCE_REMOVE
            if not viewer.load_file(filepath, prepared_path=load_path):
                self.on_file_not_opened(filepath, tab)
                return GLib.SOURCE_REMOVE
        except Exception as exc:
            self.logger.error(f"Error while loading into viewer: {exc}")
            self.on_file_not_opened(filepath, tab)
            return GLib.SOURCE_REMOVE
        finally:
            cleanup_decompressed(meshopt_temp)

        tab.filepath = filepath
        tab.file_name = os.path.basename(filepath)
        self.on_file_opened(tab)
        return GLib.SOURCE_REMOVE

    def _load_file(self, **kwargs):
        filepath = kwargs.get("filepath", None)
        override = kwargs.get("override", False)
        preserve_orientation = kwargs.get("preserve_orientation", False)
        add_file = kwargs.get("add_file", False)
        skip_auto_best = kwargs.get("_skip_auto_best", False)
        tab = kwargs.get("_tab") or self._active_tab()
        if tab is None:
            GLib.idle_add(self.on_file_not_opened, _("Unknown"), None)
            return

        viewer = tab.viewer
        camera_state = None
        if preserve_orientation:
            camera_state = viewer.get_camera_state()

        if filepath is None:
            filepath = tab.filepath or self.filepath

        if filepath == "" or filepath is None:
            GLib.idle_add(self.on_file_not_opened, _("Unknown"), tab)
            return

        resolved = self._resolve_readable_path(filepath)
        if resolved is None:
            try:
                real = os.path.realpath(filepath)
            except OSError:
                real = filepath
            self.logger.error(
                "File is not readable in sandbox: "
                f"{filepath} (realpath={real})"
            )
            GLib.idle_add(self.on_file_not_opened, filepath, tab)
            return
        if resolved != filepath:
            self.logger.info(
                f"Resolved sandbox path via realpath: {filepath} -> {resolved}"
            )
            filepath = resolved

        self.logger.debug(f"load file: {filepath}")

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
            # Settings UI must run on the main loop.
            GLib.idle_add(
                self.change_setting_state, GLib.Variant("s", settings))

        load_path = filepath
        meshopt_temp = None
        try:
            # Single prepare owner for this open; viewer skips re-prepare.
            load_path, meshopt_temp = prepare_glb_for_load(filepath)
        except MeshoptError as e:
            self.logger.error(f"Error while decompressing meshopt GLB: {e}")
            GLib.idle_add(self.on_file_not_opened, filepath, tab)
            return
        except Exception as e:
            self.logger.error(f"Error while preparing file: {e}")
            GLib.idle_add(self.on_file_not_opened, filepath, tab)
            return

        try:
            if viewer.supports(load_path):
                if add_file:
                    if not viewer.add_file(filepath, prepared_path=load_path):
                        GLib.idle_add(self.on_file_not_opened, filepath, tab)
                        return
                else:
                    if not viewer.load_file(filepath, prepared_path=load_path):
                        GLib.idle_add(self.on_file_not_opened, filepath, tab)
                        return
            else:
                GLib.idle_add(self.on_file_not_opened, filepath, tab)
                return
        except Exception as e:
            self.logger.error(f"Error while loading into viewer: {e}")
            GLib.idle_add(self.on_file_not_opened, filepath, tab)
            return
        finally:
            # Cached prepared files are not deleted here.
            cleanup_decompressed(meshopt_temp)

        if preserve_orientation and camera_state is not None:
            viewer.set_camera_state(camera_state)

        tab.filepath = filepath
        tab.file_name = os.path.basename(filepath)
        GLib.idle_add(self.on_file_opened, tab)

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
        if self.window_settings.get_setting("auto-reload").value:
            self.change_checker.run()

        self.set_title(_("Exhibit - {}").format(self.file_name))
        self.title_widget.set_subtitle(self.file_name)
        self.stack.set_visible_child_name("3d_page")
        tab.viewer.grab_focus()

        self.update_background_color()

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
        if self.window_settings.get_setting("stats-overlay").value:
            self._apply_stats_overlay(True)
        return GLib.SOURCE_REMOVE

    def on_file_not_opened(self, filepath, tab=None):
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

        if self.no_file_loaded:
            self.set_title(_("Exhibit"))
            self.stack.set_visible_child_name("startup_page")
            self.startup_stack.set_visible_child_name("error_page")
        else:
            # Return to the viewer; toast explains the failed open.
            self.stack.set_visible_child_name("3d_page")
            name = os.path.basename(str(filepath)) if filepath else _("Unknown")
            self.send_toast(_("Can't open {}").format(name))

        self.update_background_color()
        self.refresh_object_tree()
        self._mesh_stats = None
        self._update_tab_bar_visibility()

        self.block_reload = False
        return GLib.SOURCE_REMOVE

    def send_toast(self, message):
        toast = Adw.Toast(title=message, timeout=2)
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
                title="Image Saved",
                timeout=2,
                button_label="Open",
                action_name="app.show-image-externally",
                action_target=GLib.Variant("s", file_path)
            )
            self.toast_overlay.add_toast(toast)

    @Gtk.Template.Callback("on_home_clicked")
    def on_home_clicked(self, btn):
        self.f3d_viewer.reset_to_bounds()

    @Gtk.Template.Callback("on_open_button_clicked")
    def on_open_button_clicked(self, btn):
        self.open_file_chooser()

    def orthographic_state_changed(self, action, state):
        action.set_state(state)
        self.window_settings.set_setting("orthographic", state.get_boolean())
        self._update_all_viewers_options(
            {"orthographic": state.get_boolean()})

    def on_orthographic_changed(self, setting, *args):
        self.orthographic_action.set_state(
            GLib.Variant(
                "b", self.window_settings.get_setting("orthographic").value))

    def toggle_orthographic(self, *args):
        self.window_settings.set_setting(
            "orthographic",
            not self.window_settings.get_setting("orthographic").value)

    @Gtk.Template.Callback("on_drop_received")
    def on_drop_received(self, drop, value, x, y):
        dropped = value.get_files()[0]
        filepath = dropped.get_path()
        if not filepath:
            self.logger.error("Dropped file has no local path")
            self.on_file_not_opened(dropped.get_basename() or _("Unknown"))
            return

        extension = os.path.splitext(filepath)[1][1:].lower()

        if extension in image_patterns:
            self.load_hdri(filepath)
        elif extension in allowed_extensions:
            self.logger.info("drop received")
            self.load_file(filepath=filepath)

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
        try:
            file = Gio.File.new_for_path(self.filepath)
        except Exception:
            self.logger.error("Failed to construct a new Gio.File from path.")
        else:
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
        state = self.window_settings.get_setting("sidebar-show").value
        self.applying_breakpoint = True
        self.split_view.set_collapsed(False)
        self.split_view.set_show_sidebar(state)
        self.applying_breakpoint = False

    @Gtk.Template.Callback("on_split_view_show_sidebar_changed")
    def on_split_view_show_sidebar_changed(self, *args):
        if self.applying_breakpoint:
            return
        state = self.split_view.get_show_sidebar()
        self.window_settings.set_setting("sidebar-show", state)

    def on_play_button_clicked(self, btn):
        self.f3d_viewer.playing = not self.f3d_viewer.playing

    def on_playing_changed(self, *args):
        if self.f3d_viewer.playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
            self.play_button.set_tooltip_text(_("Stop"))
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")
            self.play_button.set_tooltip_text(_("Start"))

    # def on_orthographic_changed(self, *args):
    #     self.ortho_action.set_state(GLib.Variant("b", self.f3d_viewer.orthographic))
    #     self.window_settings.set_setting("orthographic", self.f3d_viewer.orthographic)

    #
    # Function called when the HDRI is deleted/added...

    def on_delete_skybox(self, *args):
        self.window_settings.set_setting("hdri-file", "")
        self.window_settings.set_setting("hdri-skybox", False)
        self.use_skybox_switch.set_active(False)
        options = {
            "hdri-file": "",
            "hdri-skybox": False}
        self._update_all_viewers_options(options)
        self.check_for_options_change()

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

    def create_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        return action

    def generate_thumbnail(self, hdri_file_path, width=300, height=200):
        base_name = os.path.basename(hdri_file_path)
        name, _ext = os.path.splitext(base_name)

        thumbnail_name = f"{name}.jpeg"
        thumbnail_filepath = os.path.join(
            self.hdri_thumbnails_path, thumbnail_name)

        with Image(filename=hdri_file_path) as img:
            img.thumbnail(width, height)
            img.gamma(1.7)
            img.brightness_contrast(0, -5)
            img.format = 'jpeg'
            img.save(filename=thumbnail_filepath)

        return thumbnail_filepath

    @Gtk.Template.Callback("on_close_request")
    def on_close_request(self, window):
        self.logger.debug("window closed, saving settings")
        self.saved_settings.set_int(
            "startup-width", window.get_width())
        self.saved_settings.set_int(
            "startup-height", window.get_height())
        self.saved_settings.set_boolean(
            "startup-sidebar-show", window.split_view.get_show_sidebar())
        self.saved_settings.set_boolean(
            "auto-best", self.window_settings.get_setting("auto-best").value)


def rgb_to_list(rgb):
    values = tuple(int(x) / 255 for x in rgb[4:-1].split(','))
    return values


def list_to_rgb(lst):
    return f"rgb({int(lst[0] * 255)},{int(lst[1] * 255)},{int(lst[2] * 255)})"


def list_files(directory):
    items = os.listdir(directory)
    files = [
        item for item in items if os.path.isfile(os.path.join(directory, item))
    ]
    return files
