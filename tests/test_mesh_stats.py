# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from exhibit.mesh_stats import collect_mesh_stats, format_overlay_text
from exhibit.meshopt_decompress import clear_prepare_cache
from tests.glb_factory import plain_triangle_gltf, write_glb


def setup_function():
    clear_prepare_cache()


def teardown_function():
    clear_prepare_cache()


def test_collect_triangle_stats(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "tri.glb", gltf, bin_chunk)
    stats = collect_mesh_stats(str(path), up="+Y")
    assert stats.vertices == 3
    assert stats.faces == 1
    assert stats.meshes == 1
    assert stats.primitives == 1
    assert stats.format == "glb"
    height = stats.resolved_height_m()
    assert height is not None
    assert height == pytest.approx(2.0, abs=1e-5)


def test_overlay_contains_counts(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "tri.glb", gltf, bin_chunk)
    stats = collect_mesh_stats(str(path))
    text = format_overlay_text(stats)
    assert "tri.glb" in text
    assert "Verts" in text
    assert "3" in text
    assert "Height" in text


def test_non_glb_size_only(tmp_path: Path):
    path = tmp_path / "box.stl"
    path.write_bytes(b"solid x\nendsolid x\n")
    stats = collect_mesh_stats(str(path))
    assert stats.format == "stl"
    assert stats.vertices is None
    assert stats.file_bytes > 0
