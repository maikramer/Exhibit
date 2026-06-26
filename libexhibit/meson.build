# Try to find libf3d_c_api first, fall back to manual linking if not found
libf3d_c_api_dep = dependency('libf3d_c_api', required: false)
libf3d_dep = dependency('libf3d', required: false)

add_project_arguments('-Wdeclaration-after-statement', language: 'c')

libexhibit_deps = [
  dependency('glib-2.0'),
  dependency('gobject-2.0'),
  dependency('gtk4'),
  dependency('graphene-1.0'),
  dependency('libdex-1'),
]

# If we found the dependencies via pkgconfig, use them
if libf3d_c_api_dep.found() and libf3d_dep.found()
  libexhibit_deps += [libf3d_c_api_dep, libf3d_dep]
endif

libexhibit_include = include_directories('.')

libexhibit_sources = [
  'exb-view.c',
  'exb-engine.c',
  'exb-utils.c',
  'exb-global.c',
  'exb-preset.c',
  'exb-presets.c',
]

libexhibit_headers = [
  'exb-view.h',
  'exb-engine.h',
  'exb-utils.h',
  'exb-global.h',
  'exb-preset.h',
  'exb-presets.h',
]

libexhibit_enums = gnome.mkenums_simple(
  'exb-enums',
  sources : libexhibit_headers
)

prefix = get_option('prefix')

datadir = join_paths(prefix, get_option('datadir'))
pkglibdir_abs = join_paths(prefix, get_option('libdir'), 'exhibit')
pkggirdir = join_paths(datadir, 'gir-1.0')
pkgtypelibdir = join_paths(get_option('libdir'), 'girepository-1.0')
pkgdatadir = join_paths(prefix, pkgdatadir)
presetsdir = join_paths(datadir, 'libexhibit', 'presets')

config_h = configuration_data()
config_h.set_quoted('DATADIR', datadir)

configure_file(
         output: 'config.h',
  configuration: config_h
)

libexhibit = library(
  'exhibit',
  libexhibit_sources,
  libexhibit_enums,
  include_directories: [libexhibit_include],
  dependencies: libexhibit_deps,
  install: true,
  version: '0.1.0',
  soversion: 0,
  c_args: [
    '-DPKGLIBDIR="@0@"'.format(pkglibdir_abs),
    '-DPKGDATADIR="@0@"'.format(pkgdatadir)
  ],
  link_args: ['-lm']
)

libexhibit_dep = declare_dependency(
  include_directories: [libexhibit_include],
  link_with: libexhibit,
  sources: libexhibit_headers,
)

gnome.generate_gir(
  libexhibit,
  sources: libexhibit_sources + libexhibit_headers + libexhibit_enums,
  namespace: 'Exb',
  nsversion: '0',
  symbol_prefix: 'exb',
  identifier_prefix: 'Exb',
  includes: ['GObject-2.0', 'GLib-2.0', 'Gtk-4.0', 'Dex-1'],
  install: true,
  install_dir_gir: pkggirdir,
  install_dir_typelib: pkgtypelibdir,
)

preset_files = files(
  'presets/3d_printing.ini',
  'presets/general.ini',
  'presets/mechanical.ini',
  'presets/point_cloud.ini',
  'presets/splat.ini',
)

install_data(
  preset_files,
  install_dir: presetsdir,
)