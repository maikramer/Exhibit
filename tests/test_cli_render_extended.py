# SPDX-License-Identifier: GPL-3.0-or-later
"""cli_render parser / job expansion / options (headless)."""

from __future__ import annotations

import argparse

import pytest

from exhibit.camera_views import PRESET_VIEWS
from exhibit.cli_render import (
    DEFAULT_BG,
    DEFAULT_LIGHT_INTENSITY,
    DEFAULT_SIZE,
    DEFAULT_VIEWS,
    XRAY_LINE_WIDTH,
    XRAY_OPACITY,
    _build_options,
    _expand_view_jobs,
    _parse_rgb,
    _parse_size,
    _parse_views,
    build_parser,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1x1", (1, 1)),
        ("1024x768", (1024, 768)),
        ("512*512", (512, 512)),
        ("800X600", (800, 600)),
        ("1920x1080", (1920, 1080)),
        ("64*32", (64, 32)),
        ("2x3", (2, 3)),
        ("4096x4096", (4096, 4096)),
    ],
)
def test_parse_size_ok(value, expected):
    assert _parse_size(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "big",
        "",
        "1024",
        "x768",
        "1024x",
        "0x100",
        "100x0",
        "-1x10",
        "10x-1",
        "axb",
        "1.5x2",
    ],
)
def test_parse_size_bad(value):
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_size(value)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0,0,0", (0.0, 0.0, 0.0)),
        ("1,1,1", (1.0, 1.0, 1.0)),
        ("0.1,0.2,0.3", (0.1, 0.2, 0.3)),
        (" 0.5 , 0.25 , 0.125 ", (0.5, 0.25, 0.125)),
        ("2,3,4", (2.0, 3.0, 4.0)),  # parser does not clamp
    ],
)
def test_parse_rgb_ok(value, expected):
    assert _parse_rgb(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "1,2", "1,2,3,4", "a,b,c", "1;2;3", "red"],
)
def test_parse_rgb_bad(value):
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_rgb(value)


@pytest.mark.parametrize("name", list(PRESET_VIEWS) + ["orbit"])
def test_parse_views_single(name: str):
    assert _parse_views(name) == [name]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("front,right", ["front", "right"]),
        ("FRONT,Left", ["front", "left"]),
        (" isometric , orbit ", ["isometric", "orbit"]),
        ("front,front", ["front", "front"]),
    ],
)
def test_parse_views_lists(value, expected):
    assert _parse_views(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "   ", "front,nope", "side", "bottom", "iso"],
)
def test_parse_views_bad(value):
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_views(value)


@pytest.mark.parametrize("orbit", [0, 1, 4, 8, 12])
def test_expand_presets_only(orbit: int):
    jobs = _expand_view_jobs(list(DEFAULT_VIEWS), orbit)
    presets = [j for j in jobs if j["kind"] == "preset"]
    orbits = [j for j in jobs if j["kind"] == "orbit"]
    assert len(presets) == len(DEFAULT_VIEWS)
    if orbit > 0:
        assert len(orbits) == orbit
    else:
        assert orbits == []


def test_expand_orbit_token_defaults_to_8():
    jobs = _expand_view_jobs(["orbit"], 0)
    assert len(jobs) == 8
    assert all(j["kind"] == "orbit" for j in jobs)
    assert jobs[0]["yaw_deg"] == pytest.approx(0.0)
    assert jobs[1]["yaw_deg"] == pytest.approx(45.0)


@pytest.mark.parametrize("n", [1, 2, 3, 6, 9])
def test_expand_orbit_yaw_spacing(n: int):
    jobs = _expand_view_jobs(["orbit"], n)
    yaws = [j["yaw_deg"] for j in jobs]
    assert len(yaws) == n
    assert yaws[0] == pytest.approx(0.0)
    if n > 1:
        assert yaws[1] == pytest.approx(360.0 / n)


def test_expand_empty_raises():
    with pytest.raises(SystemExit):
        _expand_view_jobs([], 0)


def test_build_parser_defaults_matrix():
    args = build_parser().parse_args(["m.glb", "-o", "/tmp/o"])
    assert args.size == DEFAULT_SIZE
    assert args.bg == DEFAULT_BG
    assert args.views == list(DEFAULT_VIEWS)
    assert args.up == "+Y"
    assert args.grid is True
    assert args.orbit == 0
    assert args.format == "png"
    assert args.overlay is False
    assert args.armature is False


@pytest.mark.parametrize("up", ["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
def test_build_parser_up_choices(up: str):
    # Use --up=VALUE so negative axes are not parsed as option flags.
    args = build_parser().parse_args(["m.glb", "-o", "o", f"--up={up}"])
    assert args.up == up


@pytest.mark.parametrize("up", ["-X", "-Y", "-Z"])
def test_build_parser_up_space_separated_negative_is_broken(up: str):
    """
    Real CLI bug: ``--up -X`` makes argparse treat ``-X`` as a flag.
    Users must pass ``--up=-X`` instead.
    """
    with pytest.raises(SystemExit):
        build_parser().parse_args(["m.glb", "-o", "o", "--up", up])


@pytest.mark.parametrize(
    "flag,attr",
    [
        ("--armature", "armature"),
        ("--checkerboard", "checkerboard"),
        ("--normal-glyphs", "normal_glyphs"),
        ("--display-depth", "display_depth"),
        ("--edges", "edges"),
        ("--overlay", "overlay"),
    ],
)
def test_build_parser_bool_flags(flag, attr):
    args = build_parser().parse_args(["m.glb", "-o", "o", flag])
    assert getattr(args, attr) is True


def test_build_parser_no_grid():
    args = build_parser().parse_args(["m.glb", "-o", "o", "--no-grid"])
    assert args.grid is False


def test_build_parser_custom_size_bg_views():
    args = build_parser().parse_args(
        [
            "m.glb",
            "-o",
            "o",
            "--size",
            "640x480",
            "--bg",
            "0.1,0.2,0.3",
            "--views",
            "front,orbit",
            "--orbit",
            "3",
            "--opacity",
            "0.5",
            "--line-width",
            "2.5",
            "--animation-index",
            "2",
            "--animation-time",
            "1.25",
        ]
    )
    assert args.size == (640, 480)
    assert args.bg == (0.1, 0.2, 0.3)
    assert args.views == ["front", "orbit"]
    assert args.orbit == 3
    assert args.opacity == pytest.approx(0.5)
    assert args.line_width == pytest.approx(2.5)
    assert args.animation_index == 2
    assert args.animation_time == pytest.approx(1.25)


def _ns(**kwargs) -> argparse.Namespace:
    base = dict(
        up="+Y",
        grid=True,
        bg=(1.0, 1.0, 1.0),
        edges=False,
        opacity=None,
        line_width=None,
        armature=False,
        checkerboard=False,
        normal_glyphs=False,
        display_depth=False,
        animation_index=0,
        overlay=False,
    )
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_build_options_defaults_and_xray():
    opts = _build_options(_ns())
    assert opts["scene.up_direction"] == "+Y"
    assert opts["render.grid.enable"] is True
    assert opts["model.color.opacity"] == pytest.approx(1.0)
    assert opts["render.line_width"] == pytest.approx(1.0)
    assert opts["render.light.intensity"] == pytest.approx(DEFAULT_LIGHT_INTENSITY)

    xray = _build_options(_ns(armature=True))
    assert xray["model.color.opacity"] == pytest.approx(XRAY_OPACITY)
    assert xray["render.line_width"] == pytest.approx(XRAY_LINE_WIDTH)
    assert xray["render.armature.enable"] is True


def test_build_options_explicit_opacity_with_armature():
    opts = _build_options(_ns(armature=True, opacity=0.9, line_width=7.0))
    assert opts["model.color.opacity"] == pytest.approx(0.9)
    assert opts["render.line_width"] == pytest.approx(7.0)


def test_build_options_overlay_keys():
    opts = _build_options(_ns(overlay=True), overlay_text="hello")
    assert opts["ui.filename_info"] == "hello"
    assert opts["ui.metadata"] is True


def test_build_options_overlay_flag_without_text():
    opts = _build_options(_ns(overlay=True), overlay_text=None)
    assert "ui.filename_info" not in opts


def test_render_model_manifest_smoke(tmp_path, monkeypatch):
    """Headless smoke: mock f3d.Engine, assert manifest.json shape (no GPU)."""
    import json
    import sys
    import types
    from pathlib import Path

    from exhibit.cli_render import render_model
    from tests.glb_factory import plain_triangle_gltf, write_glb

    model = write_glb(tmp_path / "tri.glb", *plain_triangle_gltf())
    out_dir = tmp_path / "out"

    class FakeImage:
        def save(self, path: str) -> None:
            Path(path).write_bytes(b"fake-png")

    class FakeCamera:
        focal_point = (0.0, 0.0, 0.0)
        position = (0.0, 0.0, 1.0)
        view_up = (0.0, 1.0, 0.0)

        def reset_to_bounds(self) -> None:
            return None

    class FakeWindow:
        def __init__(self) -> None:
            self.size = (0, 0)
            self.camera = FakeCamera()

        def render_to_image(self) -> FakeImage:
            return FakeImage()

    class FakeScene:
        def supports(self, path: str) -> bool:
            return True

        def add(self, path: str) -> None:
            return None

        def load_animation_time(self, value: float) -> None:
            return None

        def get_animation_names(self) -> list[str]:
            return []

    class FakeOptions(dict):
        def update(self, other):  # type: ignore[override]
            dict.update(self, other)

    class FakeEngine:
        def __init__(self) -> None:
            self.options = FakeOptions()
            self.scene = FakeScene()
            self.window = FakeWindow()

        @staticmethod
        def create(offscreen: bool) -> "FakeEngine":
            return FakeEngine()

        def autoload_plugins(self) -> None:
            return None

    monkeypatch.setitem(
        sys.modules, "f3d", types.SimpleNamespace(Engine=FakeEngine)
    )

    args = _ns(
        model=str(model),
        output=str(out_dir),
        views=["front"],
        orbit=0,
        overlay=False,
        size=(64, 64),
        format="png",
        animation_time=0.0,
    )
    manifest_path = render_model(args)
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

    assert data["model"] == str(model.resolve())
    assert data["prepared"] is False
    assert data["has_skins"] is False
    assert isinstance(data["animation_names"], list)
    assert "stats" in data and "primitives" in data["stats"]
    assert data["views"] == [{"name": "front", "file": "tri_front.png"}]
    assert (out_dir / "tri_front.png").is_file()
