# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from exhibit import meshopt_decompress as meshopt
from exhibit.meshopt_decompress import (
    MAX_PREPARE_CACHE_ENTRIES,
    clear_prepare_cache,
    needs_glb_prepare,
    needs_meshopt_decompress,
    prepare_glb_for_load,
    release_prepared,
    _dequant_scalar,
    _gltf_has_quantization,
    _read_glb,
    _read_glb_json,
)
from tests.glb_factory import (
    plain_triangle_gltf,
    quantized_triangle_gltf,
    write_glb,
)


@pytest.fixture(autouse=True)
def _clean_prepare_cache():
    clear_prepare_cache()
    yield
    clear_prepare_cache()


def test_needs_prepare_false_for_plain(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "plain.glb", gltf, bin_chunk)
    assert needs_glb_prepare(str(path)) is False
    assert needs_meshopt_decompress(str(path)) is False


def test_needs_prepare_false_for_non_glb(tmp_path: Path):
    path = tmp_path / "model.obj"
    path.write_text("v 0 0 0\n")
    assert needs_glb_prepare(str(path)) is False


def test_needs_prepare_true_for_quantized(tmp_path: Path):
    gltf, bin_chunk = quantized_triangle_gltf()
    path = write_glb(tmp_path / "q.glb", gltf, bin_chunk)
    assert _gltf_has_quantization(_read_glb_json(str(path)))
    assert needs_glb_prepare(str(path)) is True
    assert needs_meshopt_decompress(str(path)) is True


def test_prepare_plain_returns_same_path(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "plain.glb", gltf, bin_chunk)
    load_path, temp = prepare_glb_for_load(str(path))
    assert load_path == str(path)
    assert temp is None


def test_prepare_quantized_expands_to_float(tmp_path: Path):
    gltf, bin_chunk = quantized_triangle_gltf()
    path = write_glb(tmp_path / "q.glb", gltf, bin_chunk)
    load_path, temp = prepare_glb_for_load(str(path))
    assert temp is None  # cache-owned
    assert load_path != str(path)
    try:
        out_gltf, _ = _read_glb(load_path)
        assert "KHR_mesh_quantization" not in (out_gltf.get("extensionsUsed") or [])
        pos = out_gltf["accessors"][1]
        assert pos["componentType"] == 5126  # FLOAT
        assert pos.get("normalized") in (None, False)
    finally:
        release_prepared(load_path)


def test_prepare_cache_hit(tmp_path: Path):
    gltf, bin_chunk = quantized_triangle_gltf()
    path = write_glb(tmp_path / "q.glb", gltf, bin_chunk)
    a, _ = prepare_glb_for_load(str(path))
    b, _ = prepare_glb_for_load(str(path))
    assert a == b
    release_prepared(a)
    release_prepared(b)


def test_dequant_scalar_normalized_ubyte():
    assert _dequant_scalar(255, 5121, True) == pytest.approx(1.0)
    assert _dequant_scalar(0, 5121, True) == pytest.approx(0.0)
    assert _dequant_scalar(128, 5126, False) == pytest.approx(128.0)


def test_prepare_cache_lru_evicts(tmp_path: Path):
    paths = []
    load_paths = []
    for index in range(MAX_PREPARE_CACHE_ENTRIES + 2):
        gltf, bin_chunk = quantized_triangle_gltf()
        path = write_glb(tmp_path / f"q{index}.glb", gltf, bin_chunk)
        paths.append(path)
        load_path, _ = prepare_glb_for_load(str(path))
        load_paths.append(load_path)
        assert load_path != str(path)

    assert len(meshopt._prepare_cache) <= MAX_PREPARE_CACHE_ENTRIES
    for load_path in load_paths:
        release_prepared(load_path)


def test_prepare_cache_bytes_cap_evicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Force byte eviction while count cap would still allow both entries.
    monkeypatch.setattr(meshopt, "MAX_PREPARE_CACHE_BYTES", 1)
    load_paths = []
    for index in range(2):
        gltf, bin_chunk = quantized_triangle_gltf()
        path = write_glb(tmp_path / f"qb{index}.glb", gltf, bin_chunk)
        load_path, _ = prepare_glb_for_load(str(path))
        load_paths.append(load_path)
        assert load_path != str(path)

    assert len(meshopt._prepare_cache) == 1
    for load_path in load_paths:
        release_prepared(load_path)
