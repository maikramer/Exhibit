project('exhibit', 'c',
          version: '1.9.2',
    meson_version: '>= 1.1.0',
  default_options: [ 'c_std=gnu11',
                     'cpp_std=gnu++2a',
                     'warning_level=2',
                     'werror=false',
                   ],
)

i18n = import('i18n')
gnome = import('gnome')

subdir('data')
subdir('src')
subdir('po')
subdir('help')
subdir('libexhibit')

if get_option('thumbnailer')
    subdir('thumbnailer')
endif

gnome.post_install(
     glib_compile_schemas: true,
    gtk_update_icon_cache: true,
  update_desktop_database: true,
)
