# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from exhibit.cli_render import (
    _expand_view_jobs,
    _parse_rgb,
    _parse_size,
    _parse_views,
    build_parser,
)


def test_parse_size():
    assert _parse_size("1024x768") == (1024, 768)
    assert _parse_size("512*512") == (512, 512)
    with pytest.raises(Exception):
        _parse_size("big")


def test_parse_rgb():
    assert _parse_rgb("0.1,0.2,0.3") == (0.1, 0.2, 0.3)


def test_parse_views():
    assert _parse_views("front,isometric") == ["front", "isometric"]
    with pytest.raises(Exception):
        _parse_views("front,nope")


def test_expand_view_jobs_presets_and_orbit():
    jobs = _expand_view_jobs(["front", "orbit"], 4)
    names = [j["name"] for j in jobs]
    assert "front" in names
    assert names.count("orbit_0") == 1
    assert any(j.get("yaw_deg") == 0.0 for j in jobs if j["kind"] == "orbit")
    assert len([j for j in jobs if j["kind"] == "orbit"]) == 4


def test_expand_empty_raises():
    with pytest.raises(SystemExit):
        _expand_view_jobs([], 0)


def test_build_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["model.glb", "-o", "/tmp/out"])
    assert args.model == "model.glb"
    assert args.output == "/tmp/out"
    assert args.format == "png"
    assert args.size == (1024, 1024)


def test_build_parser_help_mentions_flatpak_ffmpeg():
    help_text = build_parser().format_help()
    assert "flatpak-spawn --host ffmpeg" in help_text
    assert "--video" in help_text
