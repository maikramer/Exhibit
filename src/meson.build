pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'exhibit'
datadir = join_paths(get_option('prefix'), get_option('datadir'))
gnome = import('gnome')

gnome.compile_resources('exhibit',
  'exhibit.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('PRESETS_PATH', 'presets')
conf.set('HDRI_PATH', 'HDRIs')
conf.set('HDRI_TN_PATH', 'HDRIs' / 'thumbnails')
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

configure_file(
  input: 'config.in',
  output: 'config.py',
  configuration: conf,
  install: true,
  install_dir: moduledir
)

exhibit_sources = [
  '__init__.py',
  'main.py',
  'window.py',
  'settings.py',
  'about_info.py',
  'window_tabs.py',
  'window_animation.py',
  'window_object_tree.py',
  'window_settings_ui.py',
  'window_load.py',
  'window_settings_io.py',
  'window_settings_react.py',
  'window_preferences.py',
  'window_chrome.py',
  'window_export.py',
  'window_file_watch.py',
  'window_inspect.py',
  'window_layout.py',
  'window_lifecycle.py',
  'vector_math.py',
  'camera_nav.py',
  'camera_fly.py',
  'camera_views.py',
  'camera_sync.py',
  'cli_render.py',
  'postfx.py',
  'mesh_stats.py',
  'logger_lib.py',
  'periodic_checker.py',
  'settings_manager.py',
  'settings_compare.py',
  'meshopt_decompress.py',
  'ktx2_transcode.py',
  'gltf_pack.py',
  'gltf_scene_graph.py',
  'drop_paths.py',
  'recent_files.py',
  'path_utils.py',
  'open_errors.py',
  'warm_load.py',
  'video_encode.py',
  'skin_weights.py',
  'color_parse.py',
  'file_patterns.py',
  'session_files.py',
]

install_data(exhibit_sources, install_dir: moduledir)
install_subdir('widgets', install_dir: moduledir,
  exclude_directories: ['__pycache__'],
  exclude_files: ['*.pyc'],
)
