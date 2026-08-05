# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for app.open-preferences (shortcuts dialog)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "main.py"
SHORTCUTS = ROOT / "src" / "shortcuts-dialog.ui"
PREFS = ROOT / "src" / "window_preferences.py"


def test_app_registers_open_preferences():
    src = MAIN.read_text(encoding="utf-8")
    assert '"open-preferences"' in src
    assert "def on_open_preferences" in src
    assert "on_preferences_clicked" in src


def test_shortcuts_dialog_lists_open_preferences_with_accel():
    ui = SHORTCUTS.read_text(encoding="utf-8")
    assert "app.open-preferences" in ui
    assert "Primary&gt;comma" in ui or "<Primary>comma" in ui


def test_window_preferences_does_not_steal_app_accel():
    src = PREFS.read_text(encoding="utf-8")
    assert 'set_accels_for_action("win.preferences"' not in src


def test_app_shortcuts_fallback_and_null_safe_folder_actions():
    src = MAIN.read_text(encoding="utf-8")
    assert "def do_startup" in src
    assert 'lookup_action("shortcuts")' in src
    assert "def on_shortcuts_action" in src
    assert "def on_open_hdri_folder" in src
    assert "def on_open_configs_folder" in src
    assert "def on_open_external" in src
    # No bare active_window.hdri_path (AttributeError when no window).
    assert "active_window.hdri_path" not in src
    assert "active_window.configs_path" not in src


def test_app_binds_logger_for_show_image_external():
    src = MAIN.read_text(encoding="utf-8")
    assert "self.logger = logger_lib.logger" in src
    assert "show-image-externally path" in src


def test_app_home_and_help_are_resilient():
    src = MAIN.read_text(encoding="utf-8")
    assert 'os.environ["HOME"]' not in src
    assert "os.path.expanduser(\"~\")" in src or "expanduser('~')" in src
    assert "help:exhibit" in src
    assert "github.com/Nokse22/Exhibit" in src
