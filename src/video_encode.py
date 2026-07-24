# SPDX-License-Identifier: GPL-3.0-or-later
"""Turntable video helpers (ffmpeg CLI; no GTK)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def write_ffmpeg_concat_list(
    frame_paths: list[str], list_path: str, *, fps: float
) -> None:
    """Write an ffmpeg concat demuxer list for still frames."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    duration = 1.0 / float(fps)
    path = Path(list_path)
    with path.open("w", encoding="utf-8") as handle:
        for frame in frame_paths:
            safe = frame.replace("'", r"'\''")
            handle.write(f"file '{safe}'\n")
            handle.write(f"duration {duration}\n")
        if frame_paths:
            safe = frame_paths[-1].replace("'", r"'\''")
            handle.write(f"file '{safe}'\n")


def _in_flatpak() -> bool:
    return bool(os.environ.get("FLATPAK_ID")) or os.path.exists("/.flatpak-info")


def _host_has_ffmpeg(spawn: str, ffmpeg: str) -> bool:
    try:
        result = subprocess.run(
            [spawn, "--host", "which", ffmpeg],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool((result.stdout or "").strip())


def resolve_ffmpeg_argv(ffmpeg: str = "ffmpeg") -> list[str]:
    """
    Return argv prefix that runs ffmpeg.

    Prefer PATH; inside Flatpak, fall back to ``flatpak-spawn --host ffmpeg``.
    """
    if shutil.which(ffmpeg):
        return [ffmpeg]
    if _in_flatpak():
        spawn = shutil.which("flatpak-spawn")
        if spawn and _host_has_ffmpeg(spawn, ffmpeg):
            return [spawn, "--host", ffmpeg]
    raise FileNotFoundError(f"{ffmpeg} not found on PATH")


def build_ffmpeg_encode_command(
    list_path: str,
    out_path: str,
    *,
    fmt: str,
    ffmpeg: str = "ffmpeg",
    ffmpeg_argv: list[str] | None = None,
) -> list[str]:
    """Return ffmpeg argv for concat list → mp4/webm."""
    if fmt == "webm":
        codec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32"]
    elif fmt == "mp4":
        codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20"]
    else:
        raise ValueError(f"unsupported video format: {fmt}")
    prefix = list(ffmpeg_argv) if ffmpeg_argv is not None else [ffmpeg]
    return [
        *prefix,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_path,
        *codec,
        out_path,
    ]


def encode_turntable_gif(
    frame_paths: list[str],
    out_path: str,
    *,
    fps: int = 24,
) -> str:
    """Encode still frames to an animated GIF via Pillow (no ffmpeg)."""
    if len(frame_paths) < 2:
        raise ValueError("need at least 2 frames for a turntable video")
    if fps <= 0:
        raise ValueError("fps must be positive")
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("Pillow (PIL) is required for GIF turntables") from exc

    frames = [Image.open(path).convert("RGBA") for path in frame_paths]
    duration_ms = max(1, int(round(1000.0 / float(fps))))
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
        disposal=2,
    )
    for frame in frames:
        frame.close()
    return out_path


def encode_turntable_video(
    frame_paths: list[str],
    out_path: str,
    *,
    fps: int = 24,
    fmt: str | None = None,
    ffmpeg: str = "ffmpeg",
) -> str:
    """
    Encode ordered still frames into a turntable video.

    ``fmt`` defaults from ``out_path`` suffix (``.mp4`` / ``.webm`` / ``.gif``).
    GIF uses Pillow; mp4/webm use ffmpeg (``FileNotFoundError`` if missing).
    """
    if len(frame_paths) < 2:
        raise ValueError("need at least 2 frames for a turntable video")
    if fmt is None:
        fmt = Path(out_path).suffix.lstrip(".").lower()
    if fmt == "gif":
        return encode_turntable_gif(frame_paths, out_path, fps=fps)

    ffmpeg_argv = resolve_ffmpeg_argv(ffmpeg)

    list_path = f"{out_path}.ffconcat"
    try:
        write_ffmpeg_concat_list(frame_paths, list_path, fps=float(fps))
        cmd = build_ffmpeg_encode_command(
            list_path,
            out_path,
            fmt=fmt,
            ffmpeg=ffmpeg,
            ffmpeg_argv=ffmpeg_argv,
        )
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    finally:
        try:
            os.unlink(list_path)
        except OSError:
            pass
    return out_path
