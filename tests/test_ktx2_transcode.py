# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from exhibit import ktx2_transcode as ktx2_mod
from exhibit.ktx2_transcode import (
    _drop_texture_basisu,
    _encode_png_rgba,
    gltf_needs_ktx2_transcode,
    ktx2_bytes_to_png,
    transcode_ktx2_in_gltf,
)
from exhibit.meshopt_decompress import (
    MeshoptError,
    clear_prepare_cache,
    needs_glb_prepare,
    prepare_glb_for_load,
    release_prepared,
    _read_glb,
)
from tests.glb_factory import basisu_fallback_gltf, write_glb

_MIP_KTX2 = Path(__file__).resolve().parent / "data" / "mip_uastc.ktx2"
_MOSS_ROCK = Path(
    "/home/maikeu/GitClones/GameDev/VibeGame/examples/simple-rpg/"
    "public/assets/meshes/moss_rock_lod0.glb"
)


def _libktx_available() -> bool:
    ktx2_mod._lib = None
    ktx2_mod._lib_failed = False
    try:
        ktx2_mod._load_library()
        return True
    except MeshoptError:
        return False


def _png_size_and_pixel0(png: bytes) -> tuple[int, int, tuple[int, int, int, int]]:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    # IHDR
    length = struct.unpack(">I", png[8:12])[0]
    assert png[12:16] == b"IHDR"
    width, height, bit_depth, color_type = struct.unpack(">IIBB", png[16:26])
    assert bit_depth == 8 and color_type == 6
    # collect IDAT
    offset = 8
    idat = bytearray()
    while offset < len(png):
        length = struct.unpack(">I", png[offset : offset + 4])[0]
        tag = png[offset + 4 : offset + 8]
        data = png[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if tag == b"IDAT":
            idat.extend(data)
        elif tag == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    stride = 1 + width * 4
    row0 = raw[1:stride]
    return width, height, (row0[0], row0[1], row0[2], row0[3])


def setup_function():
    clear_prepare_cache()


def teardown_function():
    clear_prepare_cache()


def test_encode_png_has_signature():
    png = _encode_png_rgba(2, 2, bytes([255, 0, 0, 255] * 4))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IHDR" in png
    assert b"IEND" in png


def test_drop_texture_basisu():
    texture = {
        "source": 0,
        "extensions": {"KHR_texture_basisu": {"source": 1}},
    }
    assert _drop_texture_basisu(texture) is True
    assert "extensions" not in texture
    assert texture["source"] == 0


def test_basisu_fallback_prepare_drops_extension(tmp_path: Path):
    gltf, bin_chunk = basisu_fallback_gltf()
    assert gltf_needs_ktx2_transcode(gltf)
    path = write_glb(tmp_path / "basisu.glb", gltf, bin_chunk)
    assert needs_glb_prepare(str(path)) is True
    load_path, _ = prepare_glb_for_load(str(path))
    try:
        out, _ = _read_glb(load_path)
        assert "KHR_texture_basisu" not in (out.get("extensionsUsed") or [])
        tex = out["textures"][0]
        assert "KHR_texture_basisu" not in (tex.get("extensions") or {})
        assert tex.get("source") == 0
    finally:
        release_prepared(load_path)


def test_transcode_in_memory_fallback():
    gltf, bin_chunk = basisu_fallback_gltf()
    new_bin = transcode_ktx2_in_gltf(gltf, bin_chunk)
    assert isinstance(new_bin, (bytes, bytearray))
    assert "KHR_texture_basisu" not in (gltf.get("extensionsUsed") or [])


@pytest.mark.skipif(not _MIP_KTX2.is_file(), reason="mip KTX2 fixture missing")
@pytest.mark.skipif(not _libktx_available(), reason="libktx not available")
def test_multimip_ktx2_reads_level0_not_smallest_mip():
    """Regression: mip chain is smallest-first; level0 needs GetImageOffset."""
    png = ktx2_bytes_to_png(_MIP_KTX2.read_bytes())
    width, height, pixel0 = _png_size_and_pixel0(png)
    assert (width, height) == (64, 64)
    # Fixture has a red 8x8 block at the top-left of level 0.
    assert pixel0 == (255, 0, 0, 255)


@pytest.mark.skipif(not _MOSS_ROCK.is_file(), reason="moss_rock_lod0.glb not present")
@pytest.mark.skipif(not _libktx_available(), reason="libktx not available")
def test_moss_rock_basisu_prepare_produces_png_texture():
    clear_prepare_cache()
    assert needs_glb_prepare(str(_MOSS_ROCK)) is True
    load_path, _ = prepare_glb_for_load(str(_MOSS_ROCK))
    try:
        gltf, bin_chunk = _read_glb(load_path)
        assert "KHR_texture_basisu" not in (gltf.get("extensionsUsed") or [])
        tex = gltf["textures"][0]
        assert tex.get("source") == 0
        assert "KHR_texture_basisu" not in (tex.get("extensions") or {})
        image = gltf["images"][0]
        assert image.get("mimeType") == "image/png"
        view = gltf["bufferViews"][image["bufferView"]]
        png = bin_chunk[
            view["byteOffset"] : view["byteOffset"] + view["byteLength"]
        ]
        width, height, pixel0 = _png_size_and_pixel0(png)
        assert (width, height) == (2048, 2048)
        # Matches official `ktx extract --transcode rgba8` of the embedded KTX2.
        assert pixel0 == (44, 58, 28, 255)
    finally:
        release_prepared(load_path)
