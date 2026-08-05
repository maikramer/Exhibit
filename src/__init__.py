import gi
from gi.repository import GLib

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version('Exb', '0')

# Default hint for GL; never clobber Flatpak/user GDK_DEBUG (see help FAQ).
if not GLib.getenv("GDK_DEBUG"):
    GLib.setenv("GDK_DEBUG", "gl-prefer-gl", False)
