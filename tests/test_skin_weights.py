# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for skin weight heat helpers."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from exhibit.meshopt_decompress import _read_glb
from exhibit.skin_weights import (
    HEAT_ATTR,
    cleanup_skin_weight_temp,
    gltf_has_skin_weights,
    inject_joint_weight_heat,
    list_skin_joints,
    mode_to_component,
    write_skin_weight_heat_temp,
)
from tests.glb_factory import write_glb


def _skinned_triangle() -> tuple[dict, bytes]:
    """Tiny skinned tri: verts influenced by joints 0 / 1."""
    positions = struct.pack(
        "<9f",
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
    )
    indices = struct.pack("<3H", 0, 1, 2)
    # JOINTS_0: vec4 ushort — v0→j0, v1→j1, v2→j0
    joints = struct.pack(
        "<12H",
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    # WEIGHTS_0: vec4 float
    weights = struct.pack(
        "<12f",
        1.0,
        0.0,
        0.0,
        0.0,
        0.75,
        0.25,
        0.0,
        0.0,
        0.5,
        0.5,
        0.0,
        0.0,
    )
    idx_pad = (4 - (len(indices) % 4)) % 4
    bin_chunk = indices + (b"\x00" * idx_pad)
    pos_off = len(bin_chunk)
    bin_chunk += positions
    j_off = len(bin_chunk)
    bin_chunk += joints
    w_off = len(bin_chunk)
    bin_chunk += weights
    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [2]}],
        "nodes": [
            {"name": "Root"},
            {"name": "BoneA"},
            {"name": "Mesh", "mesh": 0, "skin": 0},
        ],
        "skins": [{"joints": [0, 1], "skeleton": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 1,
                            "JOINTS_0": 2,
                            "WEIGHTS_0": 3,
                        },
                        "indices": 0,
                        "mode": 4,
                    }
                ]
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5123,
                "count": 3,
                "type": "SCALAR",
                "max": [2],
                "min": [0],
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "max": [1.0, 1.0, 0.0],
                "min": [0.0, 0.0, 0.0],
            },
            {
                "bufferView": 2,
                "componentType": 5123,
                "count": 3,
                "type": "VEC4",
                "max": [1, 0, 0, 0],
                "min": [0, 0, 0, 0],
            },
            {
                "bufferView": 3,
                "componentType": 5126,
                "count": 3,
                "type": "VEC4",
                "max": [1.0, 0.5, 0.0, 0.0],
                "min": [0.5, 0.0, 0.0, 0.0],
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(indices)},
            {"buffer": 0, "byteOffset": pos_off, "byteLength": len(positions)},
            {"buffer": 0, "byteOffset": j_off, "byteLength": len(joints)},
            {"buffer": 0, "byteOffset": w_off, "byteLength": len(weights)},
        ],
        "buffers": [{"byteLength": len(bin_chunk)}],
    }
    return gltf, bin_chunk


def test_mode_to_component():
    assert mode_to_component("magnitude") == -1
    assert mode_to_component("slot0") == 0
    assert mode_to_component("slot3") == 3
    assert mode_to_component("bone") is None
    assert mode_to_component("nope") == -1


def test_gltf_has_skin_weights_and_joints():
    gltf, _ = _skinned_triangle()
    assert gltf_has_skin_weights(gltf) is True
    joints = list_skin_joints(gltf)
    assert [j.name for j in joints] == ["Root", "BoneA"]
    assert joints[1].list_index == 1


def test_inject_joint_weight_heat(tmp_path: Path):
    gltf, bin_chunk = _skinned_triangle()
    new_bin = inject_joint_weight_heat(gltf, bin_chunk, 0)
    # Joint 0: v0=1.0; v1 slot1=0.25; v2 both slots on j0 → 1.0
    heat_acc = None
    for mesh in gltf["meshes"]:
        for prim in mesh["primitives"]:
            heat_acc = prim["attributes"][HEAT_ATTR]
    acc = gltf["accessors"][heat_acc]
    view = gltf["bufferViews"][acc["bufferView"]]
    offset = view["byteOffset"]
    heats = struct.unpack_from("<3f", new_bin, offset)
    assert heats[0] == pytest.approx(1.0)
    assert heats[1] == pytest.approx(0.25)
    assert heats[2] == pytest.approx(1.0)


def test_write_and_cleanup_heat_temp(tmp_path: Path):
    gltf, bin_chunk = _skinned_triangle()
    src = write_glb(tmp_path / "skinned.glb", gltf, bin_chunk)
    heat = write_skin_weight_heat_temp(str(src), 1)
    assert Path(heat).name.startswith("exhibit-skinw-")
    out_gltf, out_bin = _read_glb(heat)
    assert gltf_has_skin_weights(out_gltf)
    assert any(
        HEAT_ATTR in (p.get("attributes") or {})
        for m in out_gltf.get("meshes") or []
        for p in m.get("primitives") or []
    )
    # Joint 1: v0=0, v1=0.75, v2=0
    for mesh in out_gltf["meshes"]:
        for prim in mesh["primitives"]:
            ai = prim["attributes"][HEAT_ATTR]
            acc = out_gltf["accessors"][ai]
            view = out_gltf["bufferViews"][acc["bufferView"]]
            heats = struct.unpack_from("<3f", out_bin, view["byteOffset"])
            assert heats[0] == pytest.approx(0.0)
            assert heats[1] == pytest.approx(0.75)
            assert heats[2] == pytest.approx(0.0)
    cleanup_skin_weight_temp(heat)
    assert not Path(heat).exists()


def test_plain_mesh_has_no_weights():
    from tests.glb_factory import plain_triangle_gltf

    gltf, _ = plain_triangle_gltf()
    assert gltf_has_skin_weights(gltf) is False
    assert list_skin_joints(gltf) == []
