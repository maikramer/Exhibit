# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for Exb option mapping (no gi)."""

from __future__ import annotations

from pathlib import Path

VIEWER = Path(__file__).resolve().parents[1] / "src" / "widgets" / "f3d_viewer.py"


def test_update_options_handles_splat_and_unlit_keys():
    src = VIEWER.read_text(encoding="utf-8")
    assert "resolve_sprites_nick" in src
    assert 'key in ("sprites-type", "sprite-enabled")' in src
    assert 'key == "anti-aliasing"' in src
    assert '"model.unlit"' in src or "model.unlit" in src
    assert 'key == "scalar-bar"' in src or 'key == "scalar-bar"' in src.replace(
        " or key == \"scalar-bar\"", ""
    )
    # Explicit skip of scalar-bar (no Exb prop yet)
    assert "scalar-bar" in src


def test_resolve_sprites_nick_disabled_beats_type():
    text = VIEWER.read_text(encoding="utf-8")
    start = text.index("def resolve_sprites_nick")
    end = text.index("\n_UP_TO_EXB", start)
    ns: dict = {}
    exec(text[start:end], ns)  # noqa: S102 — extract pure helper without gi
    resolve = ns["resolve_sprites_nick"]

    assert (
        resolve({"sprite-enabled": False, "sprites-type": "sphere"}) == "NONE"
    )
    assert resolve({"sprite-enabled": True, "sprites-type": "gaussian"}) == (
        "GAUSSIAN"
    )
    assert resolve({"sprites-type": "circle"}) == "CIRCLE"
    assert resolve({"sprite-enabled": True}) == "SPHERE"
    assert resolve({"tone-mapping": True}) is None


def test_split_compare_copies_template_engine():
    tabs = (
        Path(__file__).resolve().parents[1] / "src" / "window_tabs.py"
    ).read_text(encoding="utf-8")
    assert tabs.count("_copy_template_engine_to_viewer(viewer)") >= 2


def test_blending_syncs_to_translucency_support_setting():
    tabs = (
        Path(__file__).resolve().parents[1] / "src" / "window_tabs.py"
    ).read_text(encoding="utf-8")
    assert '"blending": "translucency-support"' in tabs
    assert 'prop == "blending"' in tabs


def test_hdri_scene_fanout_props_sync_to_settings():
    tabs = (
        Path(__file__).resolve().parents[1] / "src" / "window_tabs.py"
    ).read_text(encoding="utf-8")
    for key in (
        '"hdri-skybox": "hdri-skybox"',
        '"hdri-file": "hdri-file"',
        '"blur-background": "blur-background"',
        '"blur-coc": "blur-coc"',
        '"edges-width": "edges-width"',
        '"model-color": "model-color"',
        '"grid-absolute": "grid-absolute"',
        '"up": "up"',
    ):
        assert key in tabs
    assert 'prop == "hdri-file"' in tabs
    assert 'prop == "up"' in tabs


def test_playing_watches_animation_adjustment_end():
    src = VIEWER.read_text(encoding="utf-8")
    assert "_watch_animation_end" in src
    assert "_on_animation_adj_end" in src
    assert 'self.notify("playing")' in src


def test_volume_inverse_maps_to_exb_props():
    src = VIEWER.read_text(encoding="utf-8")
    assert '"volume": "volume-rendering"' in src
    assert '"inverse": "volume-inverse-opacity"' in src
    tabs = (
        Path(__file__).resolve().parents[1] / "src" / "window_tabs.py"
    ).read_text(encoding="utf-8")
    assert '"volume-rendering": "volume"' in tabs
    assert '"volume-inverse-opacity": "inverse"' in tabs


def test_animation_time_syncs_exb_adjustment_seconds():
    src = VIEWER.read_text(encoding="utf-8")
    assert "seconds * 1000.0" in src
    assert 'key == "animation-time"' in src


def test_hide_reload_restores_animation_time():
    src = VIEWER.read_text(encoding="utf-8")
    assert "restore animation after hide" in src
    assert "was_playing" in src
    # Ensure we snapshot before load_file, not only camera.
    fn = src.split("def _reload_with_part_visibility", 1)[1]
    before_load = fn.split("self.load_file", 1)[0]
    assert "anim_time" in before_load


def test_load_file_keeps_sidebar_props_across_reset():
    src = VIEWER.read_text(encoding="utf-8")
    keep_block = src.split("for _prop in (", 1)[1].split("):", 1)[0]
    for prop in (
        "bloom",
        "godrays",
        "godrays-intensity",
        "ao-radius",
        "ao-intensity",
        "anti-aliasing",
        "blending",
        "show-grid",
        "background-color",
        "hdri-skybox",
        "orthographic",
    ):
        assert f'"{prop}"' in keep_block
