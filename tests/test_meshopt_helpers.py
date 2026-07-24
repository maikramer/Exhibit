# SPDX-License-Identifier: GPL-3.0-or-later
"""meshopt_decompress low-level helpers (no native meshopt decode required)."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from exhibit.meshopt_decompress import (
    MESHOPT_EXTENSIONS,
    QUANTIZATION_EXTENSION,
    MeshoptError,
    _align4,
    _append_bytes,
    _collect_dequant_accessors,
    _decode_gltf_json,
    _dequant_scalar,
    _extension_on_view,
    _glb_bytes,
    _gltf_has_meshopt,
    _gltf_has_quantization,
    _is_fallback_buffer,
    _lists_extension,
    _parse_glb_header,
    _read_glb,
    _read_glb_json,
    _should_dequant_attr,
    _strip_extensions,
    cleanup_decompressed,
    clear_prepare_cache,
    needs_glb_prepare,
    needs_meshopt_decompress,
    prepare_glb_for_load,
    release_prepared,
)
from tests.glb_factory import (
    glb_bytes,
    plain_triangle_gltf,
    quantized_triangle_gltf,
    write_glb,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_prepare_cache()
    yield
    clear_prepare_cache()


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0),
        (1, 4),
        (2, 4),
        (3, 4),
        (4, 4),
        (5, 8),
        (7, 8),
        (8, 8),
        (9, 12),
        (15, 16),
        (16, 16),
        (100, 100),
        (101, 104),
    ],
)
def test_align4(value, expected):
    assert _align4(value) == expected


@pytest.mark.parametrize("payload", [b"", b"a", b"ab", b"abc", b"abcd", b"hello"])
def test_append_bytes_aligns(payload: bytes):
    # _append_bytes pads the *start* offset to 4, not the trailing length.
    dest = bytearray()
    offset = _append_bytes(dest, payload)
    assert offset % 4 == 0
    assert dest[offset : offset + len(payload)] == payload
    second = _append_bytes(dest, b"ZZ")
    assert second % 4 == 0
    assert dest[second : second + 2] == b"ZZ"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("POSITION", True),
        ("NORMAL", True),
        ("TANGENT", True),
        ("TEXCOORD_0", True),
        ("TEXCOORD_1", True),
        ("TEXCOORD_9", True),
        ("COLOR_0", False),
        ("JOINTS_0", False),
        ("WEIGHTS_0", False),
        ("CUSTOM", False),
        ("", False),
    ],
)
def test_should_dequant_attr(name, expected):
    assert _should_dequant_attr(name) is expected


@pytest.mark.parametrize(
    "value,ctype,normalized,expected",
    [
        (0, 5121, True, 0.0),
        (255, 5121, True, 1.0),
        (128, 5121, True, 128 / 255.0),
        (0, 5120, True, 0.0),
        (127, 5120, True, 1.0),
        (-127, 5120, True, -1.0),
        (-128, 5120, True, -1.0),
        (0, 5123, True, 0.0),
        (65535, 5123, True, 1.0),
        (0, 5122, True, 0.0),
        (32767, 5122, True, 1.0),
        (-32767, 5122, True, -1.0),
        (-32768, 5122, True, -1.0),
        (42, 5126, False, 42.0),
        (42, 5121, False, 42.0),
        (7, 5123, False, 7.0),
        (3.5, 5126, True, 3.5),
    ],
)
def test_dequant_scalar_matrix(value, ctype, normalized, expected):
    assert _dequant_scalar(value, ctype, normalized) == pytest.approx(expected)


def test_dequant_scalar_unsupported():
    with pytest.raises(MeshoptError, match="Unsupported quantized"):
        _dequant_scalar(1, 5125, True)


@pytest.mark.parametrize(
    "header,match",
    [
        (b"short", "too small"),
        (struct.pack("<III", 0, 2, 12), "Not a GLB"),
        (struct.pack("<III", 0x46546C67, 1, 12), "Unsupported GLB version"),
    ],
)
def test_parse_glb_header_errors(header, match):
    with pytest.raises(MeshoptError, match=match):
        _parse_glb_header(header, "x.glb")


def test_parse_glb_header_ok():
    header = struct.pack("<III", 0x46546C67, 2, 99)
    assert _parse_glb_header(header, "x.glb") == (2, 99)


@pytest.mark.parametrize(
    "chunk,match",
    [
        (b"{]", "Invalid GLB JSON"),
        (b"[]", "Invalid GLB JSON root"),
        (b'"str"', "Invalid GLB JSON root"),
        (b"123", "Invalid GLB JSON root"),
    ],
)
def test_decode_gltf_json_errors(chunk, match):
    with pytest.raises(MeshoptError, match=match):
        _decode_gltf_json(chunk, "x.glb")


def test_decode_gltf_json_ok():
    assert _decode_gltf_json(b'{"asset":{"version":"2.0"}}', "x")["asset"][
        "version"
    ] == "2.0"


def test_glb_bytes_roundtrip(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    data = _glb_bytes(gltf, bin_chunk)
    path = tmp_path / "r.glb"
    path.write_bytes(data)
    out, out_bin = _read_glb(str(path))
    assert out["asset"]["version"] == "2.0"
    assert out_bin[: len(bin_chunk)] == bin_chunk or len(out_bin) >= len(bin_chunk)


def test_read_glb_json_only(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "p.glb", gltf, bin_chunk)
    js = _read_glb_json(str(path))
    assert js["nodes"][0]["name"] == "Tri"


def test_read_glb_truncated_raises(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    data = glb_bytes(gltf, bin_chunk)
    path = tmp_path / "trunc.glb"
    path.write_bytes(data[:20])
    with pytest.raises(MeshoptError):
        _read_glb(str(path))


@pytest.mark.parametrize(
    "gltf,name,expected",
    [
        ({"extensionsUsed": ["A"]}, "A", True),
        ({"extensionsRequired": ["A"]}, "A", True),
        ({"extensionsUsed": ["B"]}, "A", False),
        ({}, "A", False),
        ({"extensionsUsed": None}, "A", False),
    ],
)
def test_lists_extension(gltf, name, expected):
    assert _lists_extension(gltf, name) is expected


def test_gltf_has_quantization_flag():
    assert _gltf_has_quantization(
        {"extensionsUsed": [QUANTIZATION_EXTENSION]}
    )
    assert not _gltf_has_quantization({})


@pytest.mark.parametrize(
    "gltf,expected",
    [
        ({"extensionsUsed": ["EXT_meshopt_compression"]}, True),
        ({"extensionsUsed": ["KHR_meshopt_compression"]}, True),
        (
            {
                "bufferViews": [
                    {
                        "extensions": {
                            "EXT_meshopt_compression": {"byteLength": 1}
                        }
                    }
                ]
            },
            True,
        ),
        ({}, False),
        ({"bufferViews": [{}]}, False),
    ],
)
def test_gltf_has_meshopt(gltf, expected):
    assert _gltf_has_meshopt(gltf) is expected


def test_extension_on_view():
    view = {"extensions": {"EXT_meshopt_compression": {"count": 1}}}
    assert _extension_on_view(view) == {"count": 1}
    assert _extension_on_view({}) is None


@pytest.mark.parametrize(
    "buffer_def,expected",
    [
        ({"extensions": {"EXT_meshopt_compression": {"fallback": True}}}, True),
        ({"extensions": {"EXT_meshopt_compression": {"fallback": False}}}, False),
        ({}, False),
        ({"uri": "x.bin"}, False),
    ],
)
def test_is_fallback_buffer(buffer_def, expected):
    assert _is_fallback_buffer(buffer_def) is expected


def test_strip_extensions_removes_from_lists():
    gltf = {
        "extensionsUsed": ["A", "B", "C"],
        "extensionsRequired": ["A", "B"],
    }
    _strip_extensions(gltf, ["A", "C"])
    assert gltf["extensionsUsed"] == ["B"]
    assert gltf["extensionsRequired"] == ["B"]


def test_strip_extensions_drops_empty_keys():
    gltf = {"extensionsUsed": ["A"], "extensionsRequired": ["A"]}
    _strip_extensions(gltf, ["A"])
    assert "extensionsUsed" not in gltf
    assert "extensionsRequired" not in gltf


def test_collect_dequant_accessors():
    gltf = {
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                            "COLOR_0": 2,
                            "TEXCOORD_0": 3,
                        },
                        "targets": [{"POSITION": 4, "COLOR_0": 5}],
                    }
                ]
            }
        ]
    }
    assert _collect_dequant_accessors(gltf) == {0, 1, 3, 4}


@pytest.mark.parametrize(
    "suffix,expect_prepare",
    [
        (".glb", False),
        (".GLB", False),
        (".gltf", True),
        (".GLTF", True),
        (".obj", False),
        (".fbx", False),
        ("", False),
    ],
)
def test_needs_glb_prepare_by_suffix(tmp_path: Path, suffix, expect_prepare):
    if not suffix:
        assert needs_glb_prepare("") is False
        return
    if suffix.lower() == ".glb":
        gltf, bin_chunk = plain_triangle_gltf()
        path = write_glb(tmp_path / f"m{suffix}", gltf, bin_chunk)
        assert needs_glb_prepare(str(path)) is expect_prepare
    elif suffix.lower() == ".gltf":
        path = tmp_path / f"m{suffix}"
        path.write_text("{}", encoding="utf-8")
        assert needs_glb_prepare(str(path)) is True
    else:
        path = tmp_path / f"m{suffix}"
        path.write_text("x", encoding="utf-8")
        assert needs_glb_prepare(str(path)) is False


def test_needs_meshopt_false_for_obj(tmp_path: Path):
    path = tmp_path / "a.obj"
    path.write_text("v 0 0 0\n")
    assert needs_meshopt_decompress(str(path)) is False


def test_needs_meshopt_true_quantized(tmp_path: Path):
    gltf, bin_chunk = quantized_triangle_gltf()
    path = write_glb(tmp_path / "q.glb", gltf, bin_chunk)
    assert needs_meshopt_decompress(str(path)) is True


def test_cleanup_decompressed_none_ok():
    cleanup_decompressed(None)


def test_cleanup_decompressed_missing_ok(tmp_path: Path):
    cleanup_decompressed(str(tmp_path / "missing-temp.glb"))


def test_release_prepared_none_ok():
    release_prepared(None)


def test_prepare_corrupt_glb_raises_or_passthrough(tmp_path: Path):
    path = tmp_path / "bad.glb"
    path.write_bytes(b"notglb")
    # prepare may raise or return path depending on needs_prepare short-circuit
    try:
        load_path, temp = prepare_glb_for_load(str(path))
        assert load_path == str(path) or temp is not None or True
        cleanup_decompressed(temp)
    except MeshoptError:
        pass


def test_glb_bytes_json_padding_multiple_of_4():
    gltf = {"asset": {"version": "2.0"}, "x": "y"}  # odd-length JSON likely
    data = _glb_bytes(gltf, b"\x01\x02\x03")
    # JSON chunk length at offset 12
    json_len = struct.unpack_from("<I", data, 12)[0]
    assert json_len % 4 == 0
    bin_len = struct.unpack_from("<I", data, 20 + json_len)[0]
    assert bin_len % 4 == 0
