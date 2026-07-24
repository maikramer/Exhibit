# SPDX-License-Identifier: GPL-3.0-or-later
"""glb_factory + GLB IO roundtrips / invariants."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from exhibit.meshopt_decompress import (
    _GLB_MAGIC,
    _read_glb,
    _read_glb_json,
    clear_prepare_cache,
    prepare_glb_for_load,
    release_prepared,
)
from tests.glb_factory import (
    basisu_fallback_gltf,
    empty_scene_gltf,
    glb_bytes,
    multipart_gltf,
    non_indexed_triangle_gltf,
    plain_triangle_gltf,
    quantized_triangle_gltf,
    scaled_triangle_gltf,
    translated_triangle_gltf,
    triangle_indices,
    triangle_positions,
    write_glb,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_prepare_cache()
    yield
    clear_prepare_cache()


FACTORIES = [
    plain_triangle_gltf,
    multipart_gltf,
    quantized_triangle_gltf,
    basisu_fallback_gltf,
    non_indexed_triangle_gltf,
    empty_scene_gltf,
]


@pytest.mark.parametrize("factory", FACTORIES, ids=[f.__name__ for f in FACTORIES])
def test_factory_glb_roundtrip(tmp_path: Path, factory):
    gltf, bin_chunk = factory()
    path = write_glb(tmp_path / f"{factory.__name__}.glb", gltf, bin_chunk)
    out, out_bin = _read_glb(str(path))
    assert out["asset"]["version"] == "2.0"
    assert isinstance(out_bin, (bytes, bytearray))
    js = _read_glb_json(str(path))
    assert js["asset"]["version"] == "2.0"


@pytest.mark.parametrize("factory", FACTORIES, ids=[f.__name__ for f in FACTORIES])
def test_factory_glb_header_magic(tmp_path: Path, factory):
    gltf, bin_chunk = factory()
    data = glb_bytes(gltf, bin_chunk)
    magic, version, length = struct.unpack_from("<III", data, 0)
    assert magic == _GLB_MAGIC
    assert version == 2
    assert length == len(data)


@pytest.mark.parametrize(
    "translation",
    [
        [0, 0, 0],
        [1, 2, 3],
        [-1, 0.5, 10],
        [100, -100, 0],
    ],
)
def test_translated_factory(tmp_path: Path, translation):
    gltf, bin_chunk = translated_triangle_gltf(translation)
    assert gltf["nodes"][0]["translation"] == translation
    path = write_glb(tmp_path / "t.glb", gltf, bin_chunk)
    out, _ = _read_glb(str(path))
    assert out["nodes"][0]["translation"] == translation


@pytest.mark.parametrize(
    "scale",
    [
        [1, 1, 1],
        [2, 2, 2],
        [0.5, 1, 2],
        [1, 3, 1],
    ],
)
def test_scaled_factory(tmp_path: Path, scale):
    gltf, bin_chunk = scaled_triangle_gltf(scale)
    path = write_glb(tmp_path / "s.glb", gltf, bin_chunk)
    out, _ = _read_glb(str(path))
    assert out["nodes"][0]["scale"] == scale


def test_triangle_positions_layout():
    data = triangle_positions()
    assert len(data) == 36
    vals = struct.unpack("<9f", data)
    assert vals[0:3] == (0.0, 0.0, 0.0)
    assert vals[3:6] == (1.0, 0.0, 0.0)
    assert vals[6:9] == (0.0, 2.0, 0.0)


def test_triangle_indices_layout():
    assert struct.unpack("<3H", triangle_indices()) == (0, 1, 2)


@pytest.mark.parametrize("factory", FACTORIES, ids=[f.__name__ for f in FACTORIES])
def test_prepare_does_not_crash(tmp_path: Path, factory):
    gltf, bin_chunk = factory()
    path = write_glb(tmp_path / f"p_{factory.__name__}.glb", gltf, bin_chunk)
    load_path, temp = prepare_glb_for_load(str(path))
    try:
        assert Path(load_path).exists()
        _read_glb_json(load_path)
    finally:
        if temp:
            Path(temp).unlink(missing_ok=True)
        elif load_path != str(path):
            release_prepared(load_path)


@pytest.mark.parametrize("pad_extra", [0, 1, 2, 3, 4, 7])
def test_glb_bytes_bin_padding(pad_extra: int):
    gltf, _ = empty_scene_gltf()
    raw = b"x" * pad_extra
    data = glb_bytes(gltf, raw)
    # total length field
    length = struct.unpack_from("<I", data, 8)[0]
    assert length == len(data)
    assert len(data) % 4 == 0
