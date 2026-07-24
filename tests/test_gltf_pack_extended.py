# SPDX-License-Identifier: GPL-3.0-or-later
"""gltf_pack edge cases: data URIs, mime guess, errors."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from exhibit.gltf_pack import (
    _decode_data_uri,
    _guess_image_mime,
    _load_uri_bytes,
    pack_gltf_file,
    write_packed_gltf_temp,
)
from exhibit.meshopt_decompress import MeshoptError, _read_glb, clear_prepare_cache
from exhibit.ktx2_transcode import _encode_png_rgba
from tests.glb_factory import (
    plain_triangle_gltf,
    triangle_indices,
    triangle_positions,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_prepare_cache()
    yield
    clear_prepare_cache()


def _write_external(tmp_path: Path, *, with_png: bool = False) -> Path:
    positions = triangle_positions()
    indices = triangle_indices()
    idx_pad = (4 - (len(indices) % 4)) % 4
    bin_chunk = indices + (b"\x00" * idx_pad) + positions
    (tmp_path / "tri.bin").write_bytes(bin_chunk)
    gltf, _ = plain_triangle_gltf()
    gltf["buffers"] = [{"byteLength": len(bin_chunk), "uri": "tri.bin"}]
    if with_png:
        png = _encode_png_rgba(1, 1, bytes([0, 255, 0, 255]))
        (tmp_path / "tex.png").write_bytes(png)
        gltf["images"] = [{"uri": "tex.png"}]
    path = tmp_path / "tri.gltf"
    path.write_text(json.dumps(gltf), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "uri,expected",
    [
        ("data:text/plain,hello", b"hello"),
        ("data:text/plain,hello%20world", b"hello world"),
        (
            "data:application/octet-stream;base64," + base64.b64encode(b"ABC").decode(),
            b"ABC",
        ),
        (
            "data:image/png;base64," + base64.b64encode(b"\x89PNG").decode(),
            b"\x89PNG",
        ),
    ],
)
def test_decode_data_uri_ok(uri, expected):
    assert _decode_data_uri(uri) == expected


@pytest.mark.parametrize(
    "uri,match",
    [
        ("http://x", "Not a data URI"),
        ("data:broken", "Malformed data URI"),
        ("data:;base64,!!!!", "Invalid base64"),
    ],
)
def test_decode_data_uri_errors(uri, match):
    with pytest.raises(MeshoptError, match=match):
        _decode_data_uri(uri)


@pytest.mark.parametrize(
    "uri,data,expected",
    [
        ("x.png", b"\x89PNG\r\n\x1a\nxxxx", "image/png"),
        ("x.jpg", b"\xff\xd8\xff\x00", "image/jpeg"),
        ("x.jpeg", b"\xff\xd8\xff\x00", "image/jpeg"),
        ("x.ktx2", b"\xabKTX 20\xbb\r\n\x1a\n", "image/ktx2"),
        ("x.bin", b"\x00\x01\x02", None),  # non-image mime ignored
        ("tex.PNG", b"\x89PNG\r\n\x1a\n", "image/png"),
        ("noext", b"\x00\x01\x02", None),
        ("plain.txt", b"hello", None),
    ],
)
def test_guess_image_mime(uri, data, expected):
    assert _guess_image_mime(uri, data) == expected


def test_load_uri_relative(tmp_path: Path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"xyz")
    assert _load_uri_bytes(str(tmp_path), "a.bin") == b"xyz"


def test_load_uri_missing(tmp_path: Path):
    with pytest.raises(MeshoptError, match="Failed to read"):
        _load_uri_bytes(str(tmp_path), "nope.bin")


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_load_uri_remote_rejected(scheme: str):
    with pytest.raises(MeshoptError, match="Remote"):
        _load_uri_bytes("/tmp", f"{scheme}://example.com/a.bin")


def test_load_uri_unsupported_scheme():
    with pytest.raises(MeshoptError, match="Unsupported URI scheme"):
        _load_uri_bytes("/tmp", "ftp://example.com/a.bin")


def test_pack_embeds_external_png(tmp_path: Path):
    path = _write_external(tmp_path, with_png=True)
    gltf, bin_chunk = pack_gltf_file(str(path))
    assert "uri" not in gltf["buffers"][0]
    assert gltf["images"][0].get("mimeType") == "image/png"
    assert "bufferView" in gltf["images"][0]
    assert "uri" not in gltf["images"][0]
    assert len(bin_chunk) > 0


def test_pack_data_uri_buffer(tmp_path: Path):
    positions = triangle_positions()
    indices = triangle_indices()
    idx_pad = (4 - (len(indices) % 4)) % 4
    bin_chunk = indices + (b"\x00" * idx_pad) + positions
    uri = "data:application/octet-stream;base64," + base64.b64encode(bin_chunk).decode()
    gltf, _ = plain_triangle_gltf()
    gltf["buffers"] = [{"byteLength": len(bin_chunk), "uri": uri}]
    path = tmp_path / "data.gltf"
    path.write_text(json.dumps(gltf), encoding="utf-8")
    out, packed = pack_gltf_file(str(path))
    assert "uri" not in out["buffers"][0]
    assert packed[: len(bin_chunk)] == bin_chunk or len(packed) >= len(bin_chunk)


def test_pack_no_buffers_empty_bin(tmp_path: Path):
    gltf = {"asset": {"version": "2.0"}}
    path = tmp_path / "empty.gltf"
    path.write_text(json.dumps(gltf), encoding="utf-8")
    out, bin_chunk = pack_gltf_file(str(path))
    assert bin_chunk == b""
    assert out["buffers"][0]["byteLength"] == 0


def test_pack_missing_buffer_uri(tmp_path: Path):
    gltf = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 0}]}
    path = tmp_path / "bad.gltf"
    path.write_text(json.dumps(gltf), encoding="utf-8")
    with pytest.raises(MeshoptError, match="missing uri"):
        pack_gltf_file(str(path))


def test_pack_invalid_json(tmp_path: Path):
    path = tmp_path / "bad.gltf"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(MeshoptError, match="Invalid glTF JSON"):
        pack_gltf_file(str(path))


def test_pack_invalid_root_array(tmp_path: Path):
    path = tmp_path / "arr.gltf"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(MeshoptError, match="Invalid glTF root"):
        pack_gltf_file(str(path))


def test_pack_missing_file():
    with pytest.raises(MeshoptError, match="Invalid glTF JSON"):
        pack_gltf_file("/tmp/exhibit-missing-pack-12345.gltf")


def test_write_packed_gltf_temp_readable(tmp_path: Path):
    path = _write_external(tmp_path)
    packed = write_packed_gltf_temp(str(path))
    try:
        gltf, _ = _read_glb(packed)
        assert gltf["asset"]["version"] == "2.0"
    finally:
        Path(packed).unlink(missing_ok=True)


@pytest.mark.parametrize("n_buffers", [1, 2])
def test_pack_multiple_buffers(tmp_path: Path, n_buffers: int):
    chunks = [b"AAAA", b"BBBBBBBB"][:n_buffers]
    for i, chunk in enumerate(chunks):
        (tmp_path / f"b{i}.bin").write_bytes(chunk)
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [
            {"byteLength": len(c), "uri": f"b{i}.bin"} for i, c in enumerate(chunks)
        ],
        "bufferViews": [
            {"buffer": i, "byteOffset": 0, "byteLength": len(c)}
            for i, c in enumerate(chunks)
        ],
    }
    path = tmp_path / "multi.gltf"
    path.write_text(json.dumps(gltf), encoding="utf-8")
    out, packed = pack_gltf_file(str(path))
    assert len(out["buffers"]) == 1
    for view in out["bufferViews"]:
        assert view["buffer"] == 0
    assert len(packed) >= sum(len(c) for c in chunks)


def test_pack_invalid_buffer_entry(tmp_path: Path):
    gltf = {"asset": {"version": "2.0"}, "buffers": ["bad"]}
    path = tmp_path / "badbuf.gltf"
    path.write_text(json.dumps(gltf), encoding="utf-8")
    with pytest.raises(MeshoptError, match="Invalid buffer entry"):
        pack_gltf_file(str(path))
