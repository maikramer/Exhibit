# SPDX-License-Identifier: GPL-3.0-or-later
"""mesh_stats pure helpers + overlay / height edge cases."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from exhibit.mesh_stats import (
    MeshStats,
    _LazyHeight,
    _accessor_count,
    _accessor_local_aabb,
    _expand_aabb_with_oriented_box,
    _height_input_snapshot,
    _mat4_from_trs,
    _mat4_identity,
    _mat4_mul,
    _node_local_matrix,
    _scene_height_m,
    _stats_from_gltf,
    _transform_point,
    _triangle_edges,
    _world_matrices,
    collect_mesh_stats,
    format_overlay_for_f3d,
    format_overlay_text,
)
from exhibit.meshopt_decompress import clear_prepare_cache
from tests.glb_factory import (
    empty_scene_gltf,
    non_indexed_triangle_gltf,
    plain_triangle_gltf,
    scaled_triangle_gltf,
    translated_triangle_gltf,
    write_glb,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_prepare_cache()
    yield
    clear_prepare_cache()


def test_mat4_identity_diagonal():
    m = _mat4_identity()
    assert len(m) == 16
    assert m[0] == m[5] == m[10] == m[15] == 1.0
    assert sum(m) == pytest.approx(4.0)


def test_mat4_mul_identity():
    i = _mat4_identity()
    t = _mat4_from_trs([1, 2, 3], None, None)
    assert _mat4_mul(i, t) == pytest.approx(t)
    assert _mat4_mul(t, i) == pytest.approx(t)


@pytest.mark.parametrize(
    "translation,expected_tail",
    [
        ([1, 2, 3], (1.0, 2.0, 3.0)),
        ([0, 0, 0], (0.0, 0.0, 0.0)),
        ([-5, 10, 0.5], (-5.0, 10.0, 0.5)),
        (None, (0.0, 0.0, 0.0)),
    ],
)
def test_mat4_from_trs_translation(translation, expected_tail):
    m = _mat4_from_trs(translation, None, None)
    assert (m[12], m[13], m[14]) == pytest.approx(expected_tail)


@pytest.mark.parametrize(
    "scale",
    [
        [2, 2, 2],
        [1, 2, 3],
        [0.5, 1.0, 2.0],
        None,
    ],
)
def test_mat4_from_trs_scale_columns(scale):
    m = _mat4_from_trs(None, None, scale)
    sx, sy, sz = (scale + [1, 1, 1])[:3] if scale else (1.0, 1.0, 1.0)
    # Column 0 X component scaled by sx (identity rotation)
    assert abs(m[0]) == pytest.approx(float(sx))
    assert abs(m[5]) == pytest.approx(float(sy))
    assert abs(m[10]) == pytest.approx(float(sz))


def test_mat4_from_trs_identity_quat():
    m = _mat4_from_trs(None, [0, 0, 0, 1], None)
    assert m == pytest.approx(_mat4_identity())


@pytest.mark.parametrize(
    "point,expected",
    [
        ((0, 0, 0), (1, 2, 3)),
        ((1, 0, 0), (2, 2, 3)),
        ((0, 1, 0), (1, 3, 3)),
        ((0, 0, 1), (1, 2, 4)),
    ],
)
def test_transform_point_translation(point, expected):
    m = _mat4_from_trs([1, 2, 3], None, None)
    assert _transform_point(m, point) == pytest.approx(expected)


def test_node_local_matrix_prefers_matrix():
    node = {"matrix": [2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1]}
    m = _node_local_matrix(node)
    assert m[0] == 2.0
    assert m[5] == 2.0


def test_node_local_matrix_trs():
    node = {"translation": [1, 0, 0], "scale": [2, 2, 2]}
    m = _node_local_matrix(node)
    assert m[12] == pytest.approx(1.0)
    assert m[0] == pytest.approx(2.0)


def test_world_matrices_translation_chain():
    gltf = {
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {"children": [1], "translation": [1, 0, 0]},
            {"translation": [0, 2, 0], "mesh": 0},
        ],
    }
    worlds = _world_matrices(gltf)
    assert worlds[1][12] == pytest.approx(1.0)
    assert worlds[1][13] == pytest.approx(2.0)


@pytest.mark.parametrize(
    "accessor,ok",
    [
        ({"min": [0, 0, 0], "max": [1, 1, 1]}, True),
        ({"min": [0, 0], "max": [1, 1]}, False),
        ({"min": [0, 0, 0]}, False),
        ({}, False),
        ({"min": "bad", "max": [1, 1, 1]}, False),
    ],
)
def test_accessor_local_aabb(accessor, ok):
    result = _accessor_local_aabb(accessor)
    assert (result is not None) is ok


def test_expand_aabb_with_identity():
    scene_min = [math.inf, math.inf, math.inf]
    scene_max = [-math.inf, -math.inf, -math.inf]
    _expand_aabb_with_oriented_box(
        scene_min, scene_max, (0, 0, 0), (1, 2, 3), _mat4_identity()
    )
    assert scene_min == pytest.approx([0, 0, 0])
    assert scene_max == pytest.approx([1, 2, 3])


@pytest.mark.parametrize(
    "up,expected",
    [
        ("+Y", 2.0),
        ("-Y", 2.0),
        ("+X", 1.0),
        ("-X", 1.0),
        ("+Z", 0.0),
        ("-Z", 0.0),
    ],
)
def test_scene_height_plain_triangle(up, expected):
    gltf, _ = plain_triangle_gltf()
    h = _scene_height_m(gltf, up=up)
    assert h == pytest.approx(expected, abs=1e-5)


@pytest.mark.parametrize(
    "translation,up,expected",
    [
        ([0, 5, 0], "+Y", 2.0),  # translation does not change extent
        ([0, 0, 0], "+Y", 2.0),
        ([10, 0, 0], "+X", 1.0),
    ],
)
def test_scene_height_translated(translation, up, expected):
    gltf, _ = translated_triangle_gltf(translation)
    assert _scene_height_m(gltf, up=up) == pytest.approx(expected, abs=1e-5)


@pytest.mark.parametrize(
    "scale,expected_y",
    [
        ([1, 1, 1], 2.0),
        ([1, 2, 1], 4.0),
        ([1, 0.5, 1], 1.0),
        ([2, 3, 1], 6.0),
    ],
)
def test_scene_height_scaled(scale, expected_y):
    gltf, _ = scaled_triangle_gltf(scale)
    assert _scene_height_m(gltf, up="+Y") == pytest.approx(expected_y, abs=1e-5)


def test_scene_height_empty_none():
    gltf, _ = empty_scene_gltf()
    assert _scene_height_m(gltf) is None


def test_lazy_height_computes_once():
    gltf, _ = plain_triangle_gltf()
    lazy = _LazyHeight(_height_input_snapshot(gltf), up="+Y")
    a = lazy.get()
    b = lazy.get()
    assert a == pytest.approx(2.0)
    assert a == b
    assert lazy._gltf is None


def test_height_input_snapshot_drops_bin_fields():
    gltf, _ = plain_triangle_gltf()
    snap = _height_input_snapshot(gltf)
    assert "buffers" not in snap
    assert "bufferViews" not in snap
    assert "min" in snap["accessors"][1]
    assert "mesh" in snap["nodes"][0]


@pytest.mark.parametrize(
    "indices,expected_count",
    [
        ([0, 1, 2], 3),
        ([0, 1, 2, 2, 1, 3], 5),  # shared edge 1-2
        ([0, 0, 1], 1),  # degenerate edge skipped
        ([], 0),
        ([0, 1], 0),
    ],
)
def test_triangle_edges(indices, expected_count):
    assert len(_triangle_edges(indices)) == expected_count


@pytest.mark.parametrize(
    "gltf,index,expected",
    [
        ({"accessors": [{"count": 5}]}, 0, 5),
        ({"accessors": [{"count": 5}]}, 1, 0),
        ({"accessors": [{"count": 5}]}, -1, 0),
        ({"accessors": [None]}, 0, 0),
        ({"accessors": []}, 0, 0),
        ({}, 0, 0),
    ],
)
def test_accessor_count(gltf, index, expected):
    assert _accessor_count(gltf, index) == expected


def test_stats_from_gltf_non_indexed(tmp_path: Path):
    gltf, bin_chunk = non_indexed_triangle_gltf()
    path = write_glb(tmp_path / "ni.glb", gltf, bin_chunk)
    stats = _stats_from_gltf(str(path), gltf, bin_chunk)
    assert stats.vertices == 3
    assert stats.faces == 1
    assert stats.edges_approximate is True


def test_stats_from_gltf_plain_exact_edges(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "t.glb", gltf, bin_chunk)
    stats = _stats_from_gltf(str(path), gltf, bin_chunk)
    assert stats.faces == 1
    assert stats.edges == 3
    assert stats.edges_approximate is False


@pytest.mark.parametrize(
    "file_bytes,needle",
    [
        (500, "B"),
        (2048, "KiB"),
        (2 * 1024 * 1024, "MiB"),
    ],
)
def test_overlay_size_units(file_bytes, needle):
    stats = MeshStats(path="/tmp/x.glb", file_bytes=file_bytes, vertices=1)
    text = format_overlay_text(stats)
    assert needle in text
    assert "Size" in text


@pytest.mark.parametrize(
    "height,needle",
    [
        (0.005, "0.0050 m"),
        (0.05, "0.050 m"),
        (1.5, "1.50 m"),
        (150.0, "150.0 m"),
    ],
)
def test_overlay_height_precision(height, needle):
    stats = MeshStats(path="/tmp/x.glb", file_bytes=0, height_m=height)
    text = format_overlay_text(stats)
    assert needle in text


def test_overlay_approximate_edges_mark():
    stats = MeshStats(
        path="/tmp/x.glb",
        file_bytes=10,
        edges=12,
        edges_approximate=True,
        vertices=4,
        faces=2,
    )
    text = format_overlay_text(stats)
    assert "~" in text


def test_overlay_force_approximate_flag():
    stats = MeshStats(
        path="/tmp/x.glb",
        file_bytes=10,
        edges=12,
        edges_approximate=False,
        faces=2,
    )
    text = format_overlay_text(stats, approximate_edges=True)
    assert "~12" in text or "~12" in text.replace(",", "")


def test_overlay_meta_skins_anims_morph():
    stats = MeshStats(
        path="/tmp/rig.glb",
        file_bytes=100,
        meshes=1,
        primitives=1,
        materials=1,
        textures=0,
        nodes=2,
        skins=1,
        animations=2,
        morph_targets=3,
        vertices=10,
    )
    text = format_overlay_text(stats)
    assert "Skins" in text
    assert "Anims" in text
    assert "Morph" in text


def test_to_dict_resolves_lazy_height(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "t.glb", gltf, bin_chunk)
    stats = collect_mesh_stats(str(path))
    data = stats.to_dict()
    assert "_lazy_height" not in data
    assert data["height_m"] == pytest.approx(2.0, abs=1e-5)


def test_format_overlay_for_f3d_matches(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "t.glb", gltf, bin_chunk)
    stats = collect_mesh_stats(str(path))
    assert format_overlay_for_f3d(stats) == format_overlay_text(stats)


@pytest.mark.parametrize(
    "ext,fmt",
    [
        (".obj", "obj"),
        (".stl", "stl"),
        (".fbx", "fbx"),
        (".ply", "ply"),
        (".3ds", "3ds"),
        (".dae", "dae"),
        (".xyz", "xyz"),
        (".OFF", "off"),
    ],
)
def test_collect_non_gltf_format_only(tmp_path: Path, ext: str, fmt: str):
    path = tmp_path / f"model{ext}"
    path.write_bytes(b"not-a-mesh")
    stats = collect_mesh_stats(str(path))
    assert stats.format == fmt
    assert stats.vertices is None


def test_collect_missing_file():
    stats = collect_mesh_stats("/tmp/exhibit-definitely-missing-12345.glb")
    assert stats.file_bytes == 0
    assert stats.vertices is None


def test_resolved_height_none_without_lazy():
    stats = MeshStats(path="/tmp/x.glb", file_bytes=0)
    assert stats.resolved_height_m() is None
