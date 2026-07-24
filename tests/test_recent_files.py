# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from exhibit.recent_files import clear_recent, existing_recent, push_recent


def test_push_recent_dedupes_and_caps(tmp_path: Path):
    a = tmp_path / "a.glb"
    b = tmp_path / "b.glb"
    c = tmp_path / "c.glb"
    for path in (a, b, c):
        path.write_bytes(b"x")

    paths = push_recent([str(a), str(b)], str(c), max_items=2)
    assert paths == [str(c.resolve()), str(a.resolve())]

    again = push_recent(paths, str(a), max_items=3)
    assert again[0] == str(a.resolve())
    assert str(c.resolve()) in again


def test_existing_recent_filters_missing(tmp_path: Path):
    alive = tmp_path / "alive.glb"
    alive.write_bytes(b"x")
    missing = tmp_path / "gone.glb"
    assert existing_recent([str(alive), str(missing)]) == [str(alive)]


def test_clear_recent_returns_empty():
    assert clear_recent() == []
