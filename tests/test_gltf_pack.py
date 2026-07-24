# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from exhibit.gltf_pack import pack_gltf_file
from exhibit.meshopt_decompress import (
    clear_prepare_cache,
    needs_glb_prepare,
    prepare_glb_for_load,
    release_prepared,
    _read_glb,
)
from exhibit.mesh_stats import collect_mesh_stats
from tests.glb_factory import plain_triangle_gltf, triangle_indices, triangle_positions


def setup_function():
    clear_prepare_cache()


def teardown_function():
    clear_prepare_cache()


def _write_external_triangle(tmp_path: Path) -> Path:
    positions = triangle_positions()
    indices = triangle_indices()
    idx_pad = (4 - (len(indices) % 4)) % 4
    bin_chunk = indices + (b"\x00" * idx_pad) + positions
    bin_path = tmp_path / "tri.bin"
    bin_path.write_bytes(bin_chunk)

    gltf, _ = plain_triangle_gltf()
    gltf["buffers"] = [
        {"byteLength": len(bin_chunk), "uri": "tri.bin"}
    ]
    gltf_path = tmp_path / "tri.gltf"
    import json

    gltf_path.write_text(json.dumps(gltf), encoding="utf-8")
    return gltf_path


def test_needs_prepare_true_for_gltf(tmp_path: Path):
    path = _write_external_triangle(tmp_path)
    assert needs_glb_prepare(str(path)) is True


def test_pack_gltf_embeds_bin(tmp_path: Path):
    path = _write_external_triangle(tmp_path)
    gltf, bin_chunk = pack_gltf_file(str(path))
    assert "uri" not in gltf["buffers"][0]
    assert len(bin_chunk) >= 9 * 4
    assert len(gltf["bufferViews"]) >= 2


def test_prepare_gltf_then_stats(tmp_path: Path):
    path = _write_external_triangle(tmp_path)
    load_path, temp = prepare_glb_for_load(str(path))
    assert temp is None
    assert load_path != str(path)
    try:
        out, _ = _read_glb(load_path)
        assert out["asset"]["version"] == "2.0"
        stats = collect_mesh_stats(load_path, already_prepared=True)
        assert stats.vertices == 3
        assert stats.faces == 1
    finally:
        release_prepared(load_path)
