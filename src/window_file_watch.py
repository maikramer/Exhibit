# SPDX-License-Identifier: GPL-3.0-or-later
"""External file-change watcher extracted from Viewer3dWindow."""

from __future__ import annotations

from gi.repository import GLib


class FileWatchMixin:
    """Poll loaded tabs for on-disk edits and baseline mtimes."""

    def periodic_check_for_file_change(self):
        """Watch every loaded tab for external edits; never title a tab Nothing."""
        if self.block_reload:
            return any(t.loaded and t.filepath for t in self._iter_tabs())

        active = self._active_tab()
        auto = self.window_settings.get_setting("auto-reload").value

        for tab in self._iter_tabs():
            if not tab.loaded or not tab.filepath:
                continue
            disk_mtime = self._file_mtime(tab.filepath)
            if disk_mtime is None:
                continue
            if not tab.loaded_mtime:
                # First stamp after open — baseline, not a user edit.
                tab.loaded_mtime = disk_mtime
                tab.seen_disk_mtime = disk_mtime
                continue
            if disk_mtime <= tab.loaded_mtime:
                continue
            if disk_mtime <= tab.seen_disk_mtime:
                continue

            tab.seen_disk_mtime = disk_mtime
            if auto and tab is active:
                self.logger.debug(f"auto-reload {tab.filepath}")
                self._reload_tab(tab, preserve_orientation=True)
            else:
                self._mark_tab_externally_modified(tab, disk_mtime)
                if tab is active:
                    GLib.idle_add(self._prompt_reload_if_modified, tab)

        if active and active.filepath:
            mtime = self._file_mtime(active.filepath)
            if mtime is not None:
                self._cached_time_stamp = mtime

        # Keep polling while any document is open (mark/prompt even if
        # auto-reload is off).
        return any(t.loaded and t.filepath for t in self._iter_tabs())

    def update_time_stamp(self):
        """Baseline active tab mtime after a successful load (no change event)."""
        tab = self._active_tab()
        path = (tab.filepath if tab else "") or self.filepath
        mtime = self._file_mtime(path)
        if mtime is None:
            return False
        self._cached_time_stamp = mtime
        if tab is not None:
            tab.loaded_mtime = mtime
            if tab.externally_modified:
                self._clear_tab_modified(tab, mtime)
        return False

