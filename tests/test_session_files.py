# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from exhibit.session_files import (
    collect_session_paths,
    existing_session,
    session_paths_to_restore,
)


def test_collect_session_paths(tmp_path: Path):
    a = tmp_path / "a.glb"
    b = tmp_path / "b.glb"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    missing = str(tmp_path / "gone.glb")
    paths = collect_session_paths([str(a), None, str(a), missing, str(b)])
    assert paths == [str(a.resolve()), str(b.resolve())]


def test_collect_session_paths_cap(tmp_path: Path):
    files = []
    for i in range(3):
        path = tmp_path / f"{i}.glb"
        path.write_bytes(b"x")
        files.append(str(path))
    assert len(collect_session_paths(files, max_items=2)) == 2


def test_existing_session(tmp_path: Path):
    alive = tmp_path / "ok.glb"
    alive.write_bytes(b"x")
    assert existing_session([str(alive), str(tmp_path / "no.glb")]) == [
        str(alive)
    ]


def test_session_paths_to_restore(tmp_path: Path):
    alive = tmp_path / "ok.glb"
    alive.write_bytes(b"x")
    paths = [str(alive)]
    assert session_paths_to_restore(True, paths) == paths
    assert session_paths_to_restore(False, paths) == []
