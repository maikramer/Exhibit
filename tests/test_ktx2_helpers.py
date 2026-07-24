# SPDX-License-Identifier: GPL-3.0-or-later
"""ktx2_transcode helpers that do not require libktx."""

from __future__ import annotations

import pytest

from exhibit.ktx2_transcode import (
    BASISU_EXTENSION,
    _drop_texture_basisu,
    _encode_png_rgba,
    _image_is_ktx2,
    _lists_extension,
    _view_bytes,
    gltf_needs_ktx2_transcode,
    ktx2_bytes_to_png,
)
from exhibit.meshopt_decompress import MeshoptError
from tests.glb_factory import basisu_fallback_gltf, plain_triangle_gltf


@pytest.mark.parametrize(
    "w,h,pixels",
    [
        (1, 1, bytes([255, 0, 0, 255])),
        (2, 1, bytes([255, 0, 0, 255, 0, 255, 0, 255])),
        (2, 2, bytes([i % 256 for i in range(16)])),
        (4, 4, bytes([128] * 64)),
        (8, 1, bytes([1, 2, 3, 4] * 8)),
    ],
)
def test_encode_png_signature_and_chunks(w, h, pixels):
    png = _encode_png_rgba(w, h, pixels)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IHDR" in png
    assert b"IDAT" in png
    assert b"IEND" in png


@pytest.mark.parametrize("w,h", [(0, 1), (1, 0), (-1, 1), (1, -1)])
def test_encode_png_invalid_dims(w, h):
    with pytest.raises(MeshoptError, match="Invalid KTX2 dimensions"):
        _encode_png_rgba(w, h, b"\x00\x00\x00\x00")


def test_encode_png_buffer_too_small():
    with pytest.raises(MeshoptError, match="too small"):
        _encode_png_rgba(2, 2, bytes([0] * 4))


@pytest.mark.parametrize(
    "image,expected",
    [
        ({"mimeType": "image/ktx2"}, True),
        ({"mimeType": "IMAGE/KTX2"}, True),
        ({"mimeType": "image/png"}, False),
        ({"uri": "foo.ktx2"}, True),
        ({"uri": "FOO.KTX2"}, True),
        ({"uri": "foo.png"}, False),
        ({}, False),
        ({"mimeType": "image/jpeg", "uri": "x.jpg"}, False),
    ],
)
def test_image_is_ktx2(image, expected):
    assert _image_is_ktx2(image) is expected


@pytest.mark.parametrize(
    "gltf,name,expected",
    [
        ({"extensionsUsed": [BASISU_EXTENSION]}, BASISU_EXTENSION, True),
        ({"extensionsRequired": [BASISU_EXTENSION]}, BASISU_EXTENSION, True),
        ({"extensionsUsed": ["OTHER"]}, BASISU_EXTENSION, False),
        ({}, BASISU_EXTENSION, False),
    ],
)
def test_lists_extension_ktx(gltf, name, expected):
    assert _lists_extension(gltf, name) is expected


@pytest.mark.parametrize(
    "gltf,expected",
    [
        ({"extensionsUsed": [BASISU_EXTENSION]}, True),
        (
            {
                "textures": [
                    {"extensions": {BASISU_EXTENSION: {"source": 0}}}
                ]
            },
            True,
        ),
        (
            {
                "images": [{"mimeType": "image/ktx2"}],
                "textures": [{"source": 0}],
            },
            True,
        ),
        (
            {
                "images": [{"mimeType": "image/png"}],
                "textures": [{"source": 0}],
            },
            False,
        ),
        ({"images": [{"mimeType": "image/ktx2"}]}, True),
        ({}, False),
        ({"textures": ["bad"]}, False),
        ({"textures": [{}], "images": []}, False),
    ],
)
def test_gltf_needs_ktx2_transcode(gltf, expected):
    assert gltf_needs_ktx2_transcode(gltf) is expected


def test_basisu_factory_needs_transcode():
    gltf, _ = basisu_fallback_gltf()
    assert gltf_needs_ktx2_transcode(gltf) is True


def test_plain_does_not_need_ktx2():
    gltf, _ = plain_triangle_gltf()
    assert gltf_needs_ktx2_transcode(gltf) is False


@pytest.mark.parametrize(
    "texture,changed",
    [
        ({"source": 0, "extensions": {BASISU_EXTENSION: {"source": 1}}}, True),
        (
            {
                "source": 0,
                "extensions": {
                    BASISU_EXTENSION: {"source": 1},
                    "OTHER": {},
                },
            },
            True,
        ),
        ({"source": 0}, False),
        ({"extensions": {}}, False),
    ],
)
def test_drop_texture_basisu_matrix(texture, changed):
    before = "extensions" in texture and BASISU_EXTENSION in (
        texture.get("extensions") or {}
    )
    result = _drop_texture_basisu(texture)
    assert result is changed
    if changed and before:
        assert BASISU_EXTENSION not in (texture.get("extensions") or {})


def test_view_bytes_ok():
    gltf = {
        "bufferViews": [{"buffer": 0, "byteOffset": 1, "byteLength": 3}]
    }
    assert _view_bytes(gltf, b"\x00ABC\x00", 0) == b"ABC"


@pytest.mark.parametrize(
    "gltf,bin_chunk,index,match",
    [
        ({"bufferViews": []}, b"xx", 0, "Invalid bufferView index"),
        (
            {"bufferViews": [{"buffer": 1, "byteOffset": 0, "byteLength": 1}]},
            b"x",
            0,
            "self-contained",
        ),
        (
            {"bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 10}]},
            b"xx",
            0,
            "out of range",
        ),
        (
            {"bufferViews": ["bad"]},
            b"xx",
            0,
            "Invalid bufferView",
        ),
    ],
)
def test_view_bytes_errors(gltf, bin_chunk, index, match):
    with pytest.raises(MeshoptError, match=match):
        _view_bytes(gltf, bin_chunk, index)


def test_ktx2_bytes_to_png_empty():
    with pytest.raises(MeshoptError, match="Empty KTX2"):
        ktx2_bytes_to_png(b"")


def test_ktx2_bytes_to_png_not_ktx2():
    with pytest.raises(MeshoptError, match="Not a KTX2"):
        ktx2_bytes_to_png(b"\x89PNG\r\n\x1a\n")
