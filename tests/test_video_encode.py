# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from exhibit.video_encode import (
    build_ffmpeg_encode_command,
    encode_turntable_gif,
    encode_turntable_video,
    resolve_ffmpeg_argv,
    write_ffmpeg_concat_list,
)


def test_write_ffmpeg_concat_list(tmp_path: Path):
    frames = [str(tmp_path / "a.png"), str(tmp_path / "b.png")]
    list_path = tmp_path / "list.ffconcat"
    write_ffmpeg_concat_list(frames, str(list_path), fps=25)
    text = list_path.read_text(encoding="utf-8")
    assert "file '" in text
    assert "duration 0.04" in text
    assert text.count("file '") == 3  # last frame repeated


def test_build_ffmpeg_encode_command_mp4_webm():
    mp4 = build_ffmpeg_encode_command("l.txt", "out.mp4", fmt="mp4")
    assert mp4[0] == "ffmpeg"
    assert "libx264" in mp4
    webm = build_ffmpeg_encode_command("l.txt", "out.webm", fmt="webm")
    assert "libvpx-vp9" in webm
    host = build_ffmpeg_encode_command(
        "l.txt",
        "out.mp4",
        fmt="mp4",
        ffmpeg_argv=["flatpak-spawn", "--host", "ffmpeg"],
    )
    assert host[:3] == ["flatpak-spawn", "--host", "ffmpeg"]
    with pytest.raises(ValueError):
        build_ffmpeg_encode_command("l.txt", "out.gif", fmt="gif")


def test_resolve_ffmpeg_argv_prefers_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "exhibit.video_encode.shutil.which",
        lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else None,
    )
    assert resolve_ffmpeg_argv() == ["ffmpeg"]


def test_resolve_ffmpeg_argv_flatpak_host(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "exhibit.video_encode.shutil.which",
        lambda cmd: "/usr/bin/flatpak-spawn" if cmd == "flatpak-spawn" else None,
    )
    monkeypatch.setattr("exhibit.video_encode._in_flatpak", lambda: True)
    monkeypatch.setattr(
        "exhibit.video_encode._host_has_ffmpeg", lambda _spawn, _ffmpeg: True
    )
    assert resolve_ffmpeg_argv() == [
        "/usr/bin/flatpak-spawn",
        "--host",
        "ffmpeg",
    ]


def test_resolve_ffmpeg_argv_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("exhibit.video_encode.shutil.which", lambda _cmd: None)
    monkeypatch.setattr("exhibit.video_encode._in_flatpak", lambda: False)
    with pytest.raises(FileNotFoundError):
        resolve_ffmpeg_argv()


def test_encode_turntable_video_mocks_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frames = []
    for name in ("a.png", "b.png"):
        path = tmp_path / name
        path.write_bytes(b"x")
        frames.append(str(path))
    out = tmp_path / "t.mp4"

    monkeypatch.setattr(
        "exhibit.video_encode.shutil.which", lambda _cmd: "/usr/bin/ffmpeg"
    )

    calls: list[list[str]] = []

    def fake_run(cmd, check, capture_output, text):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"mp4")

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("exhibit.video_encode.subprocess.run", fake_run)
    encode_turntable_video(frames, str(out), fps=12, fmt="mp4")
    assert out.is_file()
    assert calls and "concat" in calls[0]
    assert not (tmp_path / "t.mp4.ffconcat").exists()


def test_encode_requires_two_frames(tmp_path: Path):
    with pytest.raises(ValueError):
        encode_turntable_video([str(tmp_path / "a.png")], str(tmp_path / "o.mp4"))


def test_encode_turntable_gif_pillow(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    frames = []
    for index, color in enumerate([(255, 0, 0, 255), (0, 255, 0, 255)]):
        path = tmp_path / f"f{index}.png"
        Image.new("RGBA", (8, 8), color).save(path)
        frames.append(str(path))
    out = tmp_path / "t.gif"
    encode_turntable_gif(frames, str(out), fps=10)
    assert out.is_file() and out.stat().st_size > 0


def test_encode_turntable_video_gif_fmt(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    frames = []
    for index in range(2):
        path = tmp_path / f"g{index}.png"
        Image.new("RGBA", (4, 4), (0, 0, 255, 255)).save(path)
        frames.append(str(path))
    out = tmp_path / "turn.gif"
    encode_turntable_video(frames, str(out), fps=8, fmt="gif")
    assert out.is_file()
