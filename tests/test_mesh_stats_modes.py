# SPDX-License-Identifier: GPL-3.0-or-later
"""mesh_stats face/edge counting across glTF primitive modes."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import pytest

from exhibit.mesh_stats import _stats_from_gltf
from exhibit.meshopt_decompress import clear_prepare_cache
from tests.glb_factory import write_glb


@pytest.fixture(autouse=True)
def _clean():
    clear_prepare_cache()
    yield
    clear_prepare_cache()


def _indexed_mode_gltf(
    mode: int, index_count: int, vert_count: int = 8
) -> tuple[dict[str, Any], bytes]:
    # Minimal fake buffers: indices then float positions (unused for counts).
    indices = struct.pack("<" + "H" * index_count, *range(index_count))
    idx_pad = (4 - (len(indices) % 4)) % 4
    positions = struct.pack("<" + "f" * (vert_count * 3), *([0.0] * (vert_count * 3)))
    bin_chunk = indices + (b"\x00" * idx_pad) + positions
    pos_offset = len(indices) + idx_pad
    gltf: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 1},
                        "indices": 0,
                        "mode": mode,
                    }
                ]
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5123,
                "count": index_count,
                "type": "SCALAR",
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": vert_count,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1, 1, 1],
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(indices)},
            {
                "buffer": 0,
                "byteOffset": pos_offset,
                "byteLength": len(positions),
            },
        ],
        "buffers": [{"byteLength": len(bin_chunk)}],
        "materials": [{}, {}],
        "textures": [{}],
        "animations": [{"channels": [], "samplers": []}],
        "skins": [{"joints": [0]}],
    }
    return gltf, bin_chunk


@pytest.mark.parametrize(
    "mode,index_count,expected_faces",
    [
        (4, 3, 1),  # triangles
        (4, 6, 2),
        (4, 9, 3),
        (4, 0, None),
        (5, 5, 3),  # triangle strip: max(n-2,0)
        (5, 2, None),
        (5, 3, 1),
        (6, 5, 3),  # triangle fan
        (6, 4, 2),
        (6, 2, None),
    ],
)
def test_face_counts_by_mode(
    tmp_path: Path, mode: int, index_count: int, expected_faces: int | None
):
    gltf, bin_chunk = _indexed_mode_gltf(mode, max(index_count, 1) if index_count else 1)
    # Override accessor count for index_count==0 case
    gltf["accessors"][0]["count"] = index_count
    path = write_glb(tmp_path / f"m{mode}_{index_count}.glb", gltf, bin_chunk)
    stats = _stats_from_gltf(str(path), gltf, bin_chunk)
    assert stats.faces == expected_faces
    assert stats.vertices == 8
    assert stats.materials == 2
    assert stats.textures == 1
    assert stats.animations == 1
    assert stats.skins == 1


@pytest.mark.parametrize("mode", [0, 1, 2, 3])  # points / lines family
def test_line_point_modes_no_faces(tmp_path: Path, mode: int):
    gltf, bin_chunk = _indexed_mode_gltf(mode, 6)
    path = write_glb(tmp_path / f"lp{mode}.glb", gltf, bin_chunk)
    stats = _stats_from_gltf(str(path), gltf, bin_chunk)
    assert stats.faces is None
    assert stats.vertices == 8


@pytest.mark.parametrize("prim_count", [1, 2, 3, 5])
def test_multi_primitive_vertex_sum(tmp_path: Path, prim_count: int):
    gltf, bin_chunk = _indexed_mode_gltf(4, 3, vert_count=3)
    prim = gltf["meshes"][0]["primitives"][0]
    gltf["meshes"][0]["primitives"] = [dict(prim) for _ in range(prim_count)]
    path = write_glb(tmp_path / f"mp{prim_count}.glb", gltf, bin_chunk)
    stats = _stats_from_gltf(str(path), gltf, bin_chunk)
    assert stats.primitives == prim_count
    assert stats.vertices == 3 * prim_count
    assert stats.faces == prim_count


@pytest.mark.parametrize("morph_n", [0, 1, 2, 4])
def test_morph_target_count(tmp_path: Path, morph_n: int):
    gltf, bin_chunk = _indexed_mode_gltf(4, 3, vert_count=3)
    targets = [{"POSITION": 1} for _ in range(morph_n)]
    gltf["meshes"][0]["primitives"][0]["targets"] = targets
    path = write_glb(tmp_path / f"morph{morph_n}.glb", gltf, bin_chunk)
    stats = _stats_from_gltf(str(path), gltf, bin_chunk)
    assert stats.morph_targets == (morph_n or None)


@pytest.mark.parametrize("mesh_count", [1, 2, 4])
def test_mesh_count(tmp_path: Path, mesh_count: int):
    gltf, bin_chunk = _indexed_mode_gltf(4, 3, vert_count=3)
    mesh = gltf["meshes"][0]
    gltf["meshes"] = [dict(mesh) for _ in range(mesh_count)]
    # only one node references mesh 0 — mesh count is len(meshes)
    path = write_glb(tmp_path / f"meshes{mesh_count}.glb", gltf, bin_chunk)
    stats = _stats_from_gltf(str(path), gltf, bin_chunk)
    assert stats.meshes == mesh_count
