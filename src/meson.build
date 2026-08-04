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
  'widgets/settings_dialog.py',
  'widgets/file_row.py',
  'widgets/theme_switcher.py',
]

install_data(exhibit_sources, install_dir: moduledir)
