# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

from exhibit.camera_nav import NAV_SETTING_DEFAULTS

SETTINGS = Path(__file__).resolve().parents[1] / "src" / "settings_manager.py"


def _other_settings_dict() -> dict:
    tree = ast.parse(SETTINGS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "WindowSettings":
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and len(item.targets) == 1
                    and isinstance(item.targets[0], ast.Name)
                    and item.targets[0].id == "other_settings"
                ):
                    return ast.literal_eval(item.value)
    raise AssertionError("other_settings not found")


def test_window_settings_include_nav_defaults():
    defaults = _other_settings_dict()
    for key, value in NAV_SETTING_DEFAULTS.items():
        assert key in defaults
        assert defaults[key] == value
    assert defaults["nav-invert-y"] is False
