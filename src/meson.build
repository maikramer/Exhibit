pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'exhibit'
gnome = import('gnome')

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'exhibit.in',
  output: 'exhibit',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr-xr-x'
)

exhibit_sources = [
  '__init__.py',
  'main.py',
  'window.py',
  'window_tabs.py',
  'window_animation.py',
  'window_object_tree.py',
  'window_settings_ui.py',
  'window_load.py',
  'window_settings_io.py',
  'vector_math.py',
  'camera_nav.py',
  'camera_views.py',
  'window_preferences.py',
  'cli_render.py',
  'mesh_stats.py',
  'logger_lib.py',
  'periodic_checker.py',
  'settings_manager.py',
  'meshopt_decompress.py',
  'ktx2_transcode.py',
  'gltf_pack.py',
  'drop_paths.py',
  'recent_files.py',
  'camera_sync.py',
  'path_utils.py',
  'settings_compare.py',
  'open_errors.py',
  'warm_load.py',
  'video_encode.py',
  'gltf_scene_graph.py',
  'skin_weights.py',
]

install_data(exhibit_sources, install_dir: moduledir)

install_subdir('.', install_dir: moduledir)
