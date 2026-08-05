# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import ast
from pathlib import Path

from exhibit.postfx import bloom_options_from_args, build_final_shader

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "src" / "settings_manager.py"
VIEWER = ROOT / "src" / "widgets" / "f3d_viewer.py"
TABS = ROOT / "src" / "window_tabs.py"
WINDOW_UI = ROOT / "src" / "window.ui"


def _default_settings_dict() -> dict:
    tree = ast.parse(SETTINGS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "WindowSettings":
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and len(item.targets) == 1
                    and isinstance(item.targets[0], ast.Name)
                    and item.targets[0].id == "default_settings"
                ):
                    return ast.literal_eval(item.value)
    raise AssertionError("default_settings not found")


def test_window_settings_effects_defaults():
    defaults = _default_settings_dict()
    assert defaults["bloom"] is False
    assert defaults["bloom-threshold"] == 0.25
    assert defaults["godrays"] is False
    assert defaults["godrays-intensity"] == 0.5
    assert defaults["ao-radius"] == 1.0
    assert defaults["ao-kernel-size"] == 200
    assert defaults["ao-intensity"] == 1.0


def test_update_options_maps_effect_keys():
    src = VIEWER.read_text(encoding="utf-8")
    for key in (
        '"bloom": "bloom"',
        '"godrays": "godrays"',
        '"ao-radius": "ao-radius"',
        '"ao-intensity": "ao-intensity"',
    ):
        assert key in src


def test_engine_fanout_includes_effect_props():
    src = TABS.read_text(encoding="utf-8")
    for prop in ('"bloom"', '"godrays"', '"ao-radius"', '"ao-intensity"'):
        assert prop in src
    # Fanout alone is not enough — presets need WindowSettings sync.
    mapping = src.split("_ENGINE_PROP_TO_SETTING", 1)[1].split("}", 1)[0]
    for key in (
        '"godrays": "godrays"',
        '"godrays-intensity": "godrays-intensity"',
        '"ao-radius": "ao-radius"',
        '"ao-bias": "ao-bias"',
        '"ao-kernel-size": "ao-kernel-size"',
        '"ao-intensity": "ao-intensity"',
    ):
        assert key in mapping


def test_effects_ui_uses_expander_rows():
    ui = WINDOW_UI.read_text(encoding="utf-8")
    assert 'title" translatable="yes">Effects</property>' in ui or ">Effects<" in ui
    assert 'id="ao_expander"' in ui
    assert 'id="bloom_expander"' in ui
    assert 'id="godrays_expander"' in ui
    assert 'id="aa_expander"' in ui
    assert "AdwExpanderRow" in ui
    assert 'id="ambient_occlusion_switch"' not in ui
    assert "Post-processing" not in ui


def test_build_final_shader_empty_when_off():
    assert build_final_shader(bloom=False, godrays=False) == ""


def test_build_final_shader_bloom_and_godrays():
    glsl = build_final_shader(bloom=True, godrays=True)
    assert "vec4 pixel(vec2 uv)" in glsl
    assert "texture(source," in glsl
    assert "light_pos" in glsl
    assert "near_sun" in glsl
    assert "smoothstep(threshold" in glsl
    assert "continue" not in glsl
    assert "for (int i = -4; i <= 4; i++)" in glsl
    assert "for (int i = 0; i < 32; i++)" in glsl


def test_bloom_options_from_args():
    args = argparse.Namespace(
        bloom=True,
        bloom_threshold=0.6,
        bloom_intensity=2.0,
        bloom_radius=8.0,
        godrays=True,
        godrays_intensity=0.5,
        godrays_decay=0.9,
        godrays_density=1.0,
        godrays_weight=0.4,
    )
    opts = bloom_options_from_args(args)
    assert opts["bloom"] is True
    assert opts["godrays"] is True
    assert opts["godrays-intensity"] == 0.5
