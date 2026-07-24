# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

from exhibit.path_utils import resolve_readable_path


def test_resolve_readable_path_empty_and_missing(tmp_path: Path):
    assert resolve_readable_path("") is None
    assert resolve_readable_path(str(tmp_path / "nope.glb")) is None


def test_resolve_readable_path_file(tmp_path: Path):
    path = tmp_path / "model.glb"
    path.write_bytes(b"x")
    assert resolve_readable_path(str(path)) == str(path)


def test_resolve_readable_path_follows_symlink(tmp_path: Path):
    target = tmp_path / "real.glb"
    target.write_bytes(b"y")
    link = tmp_path / "link.glb"
    try:
        link.symlink_to(target)
    except OSError:
        # Some hosts disallow symlinks; skip quietly.
        return
    resolved = resolve_readable_path(str(link))
    assert resolved in {str(link), str(target.resolve())}
    assert os.path.isfile(resolved)
