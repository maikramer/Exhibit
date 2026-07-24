# SPDX-License-Identifier: GPL-3.0-or-later
"""Simple GLib timeout poller used for file-change checks."""

from __future__ import annotations

import logging

from gi.repository import GLib, GObject

_log = logging.getLogger(__name__)


class PeriodicChecker(GObject.Object):
    def __init__(self, function):
        super().__init__()

        self._running = False
        self._source_id = 0
        self._function = function

    def run(self):
        if self._running:
            return
        self._running = True
        self._source_id = GLib.timeout_add(500, self.periodic_check)

    def stop(self):
        self._running = False
        if self._source_id:
            try:
                GLib.source_remove(self._source_id)
            except Exception as exc:
                # Source may already be gone after a prior tick.
                _log.debug("PeriodicChecker.stop source_remove: %s", exc)
            self._source_id = 0

    def periodic_check(self):
        if self._running:
            self._function()
            return True
        self._source_id = 0
        return False
