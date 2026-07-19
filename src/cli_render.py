# cli_render.py
#
# Copyright 2024-2026 Nokse <nokse@posteo.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Headless multi-angle render CLI for AI / agent model analysis."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import f3d

from .camera_views import PRESET_VIEWS, UP_DIRS, apply_orbit, apply_view
from .gltf_scene_graph import glb_has_skins
from .mesh_stats import collect_mesh_stats, format_overlay_for_f3d
from .meshopt_decompress import MeshoptError, cleanup_decompressed, prepare_glb_for_load

DEFAULT_VIEWS = ("front", "right", "back", "left", "top", "isometric")
DEFAULT_SIZE = (1024, 1024)
DEFAULT_BG = (0.12, 0.12, 0.12)
XRAY_OPACITY = 0.35
XRAY_LINE_WIDTH = 4.0


def _parse_size(value: str) -> tuple[int, int]:
    text = value.lower().replace("*", "x")
    if "x" not in text:
        raise argparse.ArgumentTypeError("size must be WxH, e.g. 1024x1024")
    width_s, height_s = text.split("x", 1)
    try:
        width, height = int(width_s), int(height_s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must be WxH integers") from exc
    if width < 1 or height < 1:
        raise argparse.ArgumentTypeError("size must be positive")
    return width, height


def _parse_rgb(value: str) -> tuple[float, float, float]:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("bg must be R,G,B floats in 0..1")
    try:
        rgb = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bg must be R,G,B floats") from exc
    return rgb  # type: ignore[return-value]


def _parse_views(value: str) -> list[str]:
    names = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not names:
        raise argparse.ArgumentTypeError("views list is empty")
    allowed = set(PRESET_VIEWS) | {"orbit"}
    for name in names:
        if name not in allowed:
            raise argparse.ArgumentTypeError(
                f"unknown view {name!r}; choose from {', '.join(sorted(allowed))}"
            )
    return names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exhibit render",
        description=(
            "Render a 3D model from multiple camera angles for analysis "
            "(PNG + manifest.json)."
        ),
    )
    parser.add_argument("model", help="Path to the model file (glb, fbx, obj, …)")
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        dest="output",
        help="Output directory for PNGs and manifest.json",
    )
    parser.add_argument(
        "--views",
        type=_parse_views,
        default=list(DEFAULT_VIEWS),
        help=(
            "Comma-separated presets: front,right,back,left,top,isometric "
            f"(default: {','.join(DEFAULT_VIEWS)}). Use 'orbit' with --orbit."
        ),
    )
    parser.add_argument(
        "--orbit",
        type=int,
        metavar="N",
        default=0,
        help="Add N orbit yaw steps (0..N-1). Also used when --views includes orbit.",
    )
    parser.add_argument(
        "--size",
        type=_parse_size,
        default=DEFAULT_SIZE,
        help="Output size WxH (default: 1024x1024)",
    )
    parser.add_argument(
        "--up",
        choices=sorted(UP_DIRS.keys()),
        default="+Y",
        help="Scene up direction (default: +Y)",
    )
    parser.add_argument(
        "--armature",
        action="store_true",
        help="Show glTF armature with X-ray defaults (opacity/line-width)",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        default=None,
        help="Model opacity 0..1 (default: 1, or 0.35 with --armature)",
    )
    parser.add_argument(
        "--line-width",
        type=float,
        default=None,
        dest="line_width",
        help="Line width (default: 1, or 4 with --armature)",
    )
    parser.add_argument(
        "--edges",
        action="store_true",
        help="Show mesh edges",
    )
    parser.add_argument(
        "--grid",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Show ground grid (default: off)",
    )
    parser.add_argument(
        "--bg",
        type=_parse_rgb,
        default=DEFAULT_BG,
        help="Background RGB 0..1 (default: 0.12,0.12,0.12)",
    )
    parser.add_argument(
        "--animation-index",
        type=int,
        default=0,
        dest="animation_index",
        help="Animation clip index (default: 0)",
    )
    parser.add_argument(
        "--animation-time",
        type=float,
        default=0.0,
        dest="animation_time",
        help="Animation time in seconds (default: 0)",
    )
    parser.add_argument(
        "--format",
        choices=("png",),
        default="png",
        help="Image format (only png for now)",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Burn mesh stats into PNGs (F3D filename/metadata overlay)",
    )
    return parser


def _build_options(
    args: argparse.Namespace, *, overlay_text: str | None = None
) -> dict[str, Any]:
    opacity = args.opacity
    line_width = args.line_width
    if args.armature:
        if opacity is None:
            opacity = XRAY_OPACITY
        if line_width is None:
            line_width = XRAY_LINE_WIDTH
    if opacity is None:
        opacity = 1.0
    if line_width is None:
        line_width = 1.0

    options: dict[str, Any] = {
        "scene.up_direction": args.up,
        "render.grid.enable": bool(args.grid),
        "render.background.color": list(args.bg),
        "render.background.skybox": False,
        "render.hdri.ambient": False,
        "render.show_edges": bool(args.edges),
        "render.line_width": float(line_width),
        "model.color.opacity": float(opacity),
        "render.armature.enable": bool(args.armature),
        "scene.animation.indices": [int(args.animation_index)],
        "render.effect.antialiasing.mode": "fxaa",
        "render.effect.tone_mapping": True,
    }
    if args.overlay and overlay_text:
        options.update(
            {
                "ui.metadata": True,
                "ui.filename": True,
                "ui.filename_info": overlay_text,
                "ui.backdrop.opacity": 0.55,
            }
        )
    return options


def _expand_view_jobs(
    views: list[str], orbit: int
) -> list[dict[str, Any]]:
    """Expand CLI view list into concrete render jobs."""
    jobs: list[dict[str, Any]] = []
    want_orbit = orbit > 0 or "orbit" in views
    for name in views:
        if name == "orbit":
            continue
        jobs.append({"name": name, "kind": "preset"})
    if want_orbit:
        count = orbit if orbit > 0 else 8
        for index in range(count):
            yaw = (360.0 * index) / count
            jobs.append(
                {
                    "name": f"orbit_{index}",
                    "kind": "orbit",
                    "yaw_deg": yaw,
                }
            )
    if not jobs:
        raise SystemExit("No views to render (empty --views / --orbit)")
    return jobs


def render_model(args: argparse.Namespace) -> str:
    model_path = os.path.abspath(args.model)
    if not os.path.isfile(model_path):
        raise SystemExit(f"Model not found: {model_path}")

    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(model_path))[0]
    jobs = _expand_view_jobs(list(args.views), int(args.orbit))

    print(f"Loading {model_path}", file=sys.stderr)
    load_path = model_path
    prepare_temp = None
    prepared = False
    try:
        load_path, prepare_temp = prepare_glb_for_load(model_path)
        prepared = load_path != model_path
    except MeshoptError as exc:
        raise SystemExit(f"Failed to prepare model: {exc}") from exc

    print("Collecting mesh stats", file=sys.stderr)
    stats = collect_mesh_stats(load_path, already_prepared=True)
    overlay_text = format_overlay_for_f3d(stats) if args.overlay else None
    options = _build_options(args, overlay_text=overlay_text)

    eng = f3d.Engine.create(True)
    eng.autoload_plugins()
    eng.options.update(options)

    if not eng.scene.supports(load_path):
        cleanup_decompressed(prepare_temp)
        raise SystemExit(f"Unsupported model format: {model_path}")

    try:
        eng.scene.add(load_path)
    except Exception as exc:
        cleanup_decompressed(prepare_temp)
        raise SystemExit(f"Failed to load model: {exc}") from exc

    # Keep prepared file until after load; cache may own it (temp=None).
    cleanup_decompressed(prepare_temp)

    width, height = args.size
    eng.window.size = (width, height)

    try:
        eng.scene.load_animation_time(float(args.animation_time))
    except Exception:
        pass

    animation_names: list[str] = []
    try:
        animation_names = list(eng.scene.get_animation_names())
    except Exception:
        animation_names = []

    has_skins = glb_has_skins(model_path)

    view_entries: list[dict[str, Any]] = []
    for job in jobs:
        name = job["name"]
        if job["kind"] == "preset":
            apply_view(eng.window.camera, name, up=args.up)
        else:
            apply_orbit(eng.window.camera, float(job["yaw_deg"]), up=args.up)

        filename = f"{stem}_{name}.{args.format}"
        out_path = os.path.join(out_dir, filename)
        print(f"Rendering {name} -> {out_path}", file=sys.stderr)
        image = eng.window.render_to_image()
        image.save(out_path)

        entry: dict[str, Any] = {"name": name, "file": filename}
        if "yaw_deg" in job:
            entry["yaw_deg"] = job["yaw_deg"]
        view_entries.append(entry)

    manifest = {
        "model": model_path,
        "prepared": prepared,
        "has_skins": has_skins,
        "animation_names": animation_names,
        "stats": stats.to_dict(),
        "options": {
            "armature": bool(args.armature),
            "opacity": options["model.color.opacity"],
            "line_width": options["render.line_width"],
            "edges": bool(args.edges),
            "grid": bool(args.grid),
            "overlay": bool(args.overlay),
            "size": [width, height],
            "up": args.up,
            "bg": list(args.bg),
            "animation_index": int(args.animation_index),
            "animation_time": float(args.animation_time),
        },
        "views": view_entries,
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest_path = render_model(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # One line on stdout for agent pipelines.
    print(manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
