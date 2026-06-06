# Try to find libf3d_c_api first, fall back to manual linking if not found
libf3d_c_api_dep = dependency('libf3d_c_api', required: false)
libf3d_dep = dependency('libf3d', required: false)

libexhibit_deps = [
  dependency('glib-2.0'),
  dependency('gobject-2.0'),
  dependency('gtk4'),
  dependency('graphene-1.0')
]

# If we found the dependencies via pkgconfig, use them
if libf3d_c_api_dep.found() and libf3d_dep.found()
  libexhibit_deps += [libf3d_c_api_dep, libf3d_dep]
endif

libexhibit_include = include_directories('.')

libexhibit_sources = [
  'exb-view.c',
  'exb-engine.c',
]

libexhibit_headers = [
  'exb-view.h',
  'exb-engine.h',
]

pkglibdir_abs = join_paths(get_option('prefix'), get_option('libdir'), 'exhibit')
pkggirdir = join_paths(get_option('datadir'), 'gir-1.0')
pkgtypelibdir = join_paths(get_option('libdir'), 'girepository-1.0')

libexhibit = library(
  'exhibit',
  libexhibit_sources,
  include_directories: [libexhibit_include],
  dependencies: libexhibit_deps,
  install: true,
  version: '0.1.0',
  soversion: 0,
  c_args: [
    '-DPKGLIBDIR="@0@"'.format(pkglibdir_abs),
    '-DPKGDATADIR="@0@"'.format(join_paths(get_option('prefix'), pkgdatadir))
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
  sources: libexhibit_sources + libexhibit_headers,
  namespace: 'Exb',
  nsversion: '0',
  symbol_prefix: 'exb',
  identifier_prefix: 'Exb',
  includes: ['GObject-2.0', 'GLib-2.0', 'Gtk-4.0'],
  install: true,
  install_dir_gir: pkggirdir,
  install_dir_typelib: pkgtypelibdir,
)
