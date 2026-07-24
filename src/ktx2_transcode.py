# ktx2_transcode.py
#
# Copyright 2024-2025 Nokse <nokse@posteo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Transcode KTX2 / KHR_texture_basisu images to PNG for F3D/VTK."""

from __future__ import annotations

import os
import struct
import zlib
from ctypes import (
    CDLL,
    POINTER,
    Structure,
    byref,
    c_bool,
    c_char_p,
    c_int,
    c_size_t,
    c_ubyte,
    c_uint32,
    c_void_p,
    cast,
)
from ctypes.util import find_library
from pathlib import Path
from typing import Any

BASISU_EXTENSION = "KHR_texture_basisu"

_KTX_TEXTURE_CREATE_LOAD_IMAGE_DATA_BIT = 0x01
_KTX_TTF_RGBA32 = 13
_KTX_SUCCESS = 0

_lib: CDLL | None = None
_lib_failed = False


class _KtxOrientation(Structure):
    _fields_ = [
        ("x", c_int),
        ("y", c_int),
        ("z", c_int),
    ]


class _KtxTexture(Structure):
    """Partial layout of ktxTexture (x86_64 / aarch64 Linux)."""

    _fields_ = [
        ("classId", c_int),
        ("vtbl", c_void_p),
        ("vvtbl", c_void_p),
        ("_protected", c_void_p),
        ("isArray", c_bool),
        ("isCubemap", c_bool),
        ("isCompressed", c_bool),
        ("generateMipmaps", c_bool),
        ("baseWidth", c_uint32),
        ("baseHeight", c_uint32),
        ("baseDepth", c_uint32),
        ("numDimensions", c_uint32),
        ("numLevels", c_uint32),
        ("numLayers", c_uint32),
        ("numFaces", c_uint32),
        ("orientation", _KtxOrientation),
        ("kvDataHead", c_void_p),
        ("kvDataLen", c_uint32),
        ("kvData", c_void_p),
        ("dataSize", c_size_t),
        ("pData", c_void_p),
    ]


def _error(message: str) -> Exception:
    # Local import avoids circular dependency with meshopt_decompress.
    from .meshopt_decompress import MeshoptError

    return MeshoptError(message)


def _library_candidates() -> list[str]:
    """Ordered libktx shared-object names / paths to try."""
    candidates: list[str] = []

    for env_key in ("LIBKTX", "KTX_LIBRARY"):
        value = os.environ.get(env_key)
        if value:
            candidates.append(value)

    for part in os.environ.get("LD_LIBRARY_PATH", "").split(":"):
        if not part:
            continue
        root = Path(part)
        candidates.extend(
            [
                str(root / "libktx.so"),
                str(root / "libktx.so.4"),
                str(root / "libktx.so.0"),
            ]
        )

    found = find_library("ktx")
    if found:
        candidates.append(found)

    home = Path.home()
    candidates.extend(
        [
            "ktx",
            "libktx.so",
            "libktx.so.4",
            "libktx.so.0",
            "/app/lib/libktx.so",
            "/usr/lib/libktx.so",
            "/usr/lib64/libktx.so",
            "/usr/local/lib/libktx.so",
            str(home / ".local/opt/KTX-Software/lib/libktx.so"),
            str(home / ".local/lib/libktx.so"),
        ]
    )

    # Preserve order while dropping empties / duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _load_library() -> CDLL:
    global _lib, _lib_failed
    if _lib is not None:
        return _lib
    if _lib_failed:
        raise _error("libktx is not available")

    last_error: Exception | None = None
    for name in _library_candidates():
        try:
            lib = CDLL(name)
        except OSError as exc:
            last_error = exc
            continue
        _configure_lib(lib)
        _lib = lib
        return lib

    _lib_failed = True
    raise _error(
        "libktx is not available; cannot open KTX2 / BasisU textures"
    ) from last_error


def _configure_lib(lib: CDLL) -> None:
    lib.ktxTexture_CreateFromMemory.argtypes = [
        POINTER(c_ubyte),
        c_size_t,
        c_uint32,
        POINTER(c_void_p),
    ]
    lib.ktxTexture_CreateFromMemory.restype = c_int

    if hasattr(lib, "ktxTexture2_CreateFromMemory"):
        lib.ktxTexture2_CreateFromMemory.argtypes = [
            POINTER(c_ubyte),
            c_size_t,
            c_uint32,
            POINTER(c_void_p),
        ]
        lib.ktxTexture2_CreateFromMemory.restype = c_int

    lib.ktxTexture_GetData.argtypes = [c_void_p]
    lib.ktxTexture_GetData.restype = c_void_p

    lib.ktxTexture_GetRowPitch.argtypes = [c_void_p, c_uint32]
    lib.ktxTexture_GetRowPitch.restype = c_uint32

    lib.ktxTexture2_GetImageOffset.argtypes = [
        c_void_p,
        c_uint32,
        c_uint32,
        c_uint32,
        POINTER(c_size_t),
    ]
    lib.ktxTexture2_GetImageOffset.restype = c_int

    lib.ktxTexture2_GetImageSize.argtypes = [c_void_p, c_uint32]
    lib.ktxTexture2_GetImageSize.restype = c_size_t

    lib.ktxTexture2_NeedsTranscoding.argtypes = [c_void_p]
    lib.ktxTexture2_NeedsTranscoding.restype = c_bool

    lib.ktxTexture2_TranscodeBasis.argtypes = [c_void_p, c_int, c_uint32]
    lib.ktxTexture2_TranscodeBasis.restype = c_int

    lib.ktxTexture2_Destroy.argtypes = [c_void_p]
    lib.ktxTexture2_Destroy.restype = None

    lib.ktxErrorString.argtypes = [c_int]
    lib.ktxErrorString.restype = c_char_p


def _ktx_error(lib: CDLL, code: int, context: str) -> Exception:
    message = lib.ktxErrorString(code)
    detail = message.decode("utf-8", errors="replace") if message else str(code)
    return _error(f"{context}: {detail}")


def _encode_png_rgba(width: int, height: int, rgba: bytes) -> bytes:
    if width <= 0 or height <= 0:
        raise _error(f"Invalid KTX2 dimensions: {width}x{height}")
    expected = width * height * 4
    if len(rgba) < expected:
        raise _error(f"KTX2 RGBA buffer too small ({len(rgba)} < {expected})")

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag)
        crc = zlib.crc32(data, crc) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = bytearray()
    stride = width * 4
    for row in range(height):
        start = row * stride
        raw.append(0)
        raw.extend(rgba[start : start + stride])

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


_KTX2_IDENTIFIER = b"\xabKTX 20\xbb\r\n\x1a\n"


def _level0_rgba32(lib: CDLL, texture_ptr: c_void_p) -> tuple[int, int, bytes]:
    """
    Return ``(width, height, tightly-packed RGBA8)`` for mip level 0.

    KTX2 stores mip levels smallest-first in ``pData``. Reading from offset 0
    therefore yields garbage when ``numLevels > 1`` — use GetImageOffset.
    """
    texture = cast(texture_ptr, POINTER(_KtxTexture)).contents
    width = int(texture.baseWidth)
    height = int(texture.baseHeight)
    if width <= 0 or height <= 0 or width > 65536 or height > 65536:
        raise _error(f"Invalid KTX2 dimensions: {width}x{height}")

    data_ptr = lib.ktxTexture_GetData(texture_ptr)
    data_addr = int(data_ptr) if data_ptr else 0
    if not data_addr:
        raise _error("ktxTexture_GetData returned NULL")

    offset = c_size_t(0)
    rc = lib.ktxTexture2_GetImageOffset(texture_ptr, 0, 0, 0, byref(offset))
    if rc != _KTX_SUCCESS:
        raise _ktx_error(lib, rc, "ktxTexture2_GetImageOffset failed")

    image_size = int(lib.ktxTexture2_GetImageSize(texture_ptr, 0))
    row_pitch = int(lib.ktxTexture_GetRowPitch(texture_ptr, 0))
    tight_stride = width * 4
    expected = tight_stride * height
    data_size = int(texture.dataSize)

    if image_size <= 0:
        raise _error("ktxTexture2_GetImageSize returned 0 for level 0")
    if row_pitch < tight_stride:
        raise _error(
            f"KTX2 rowPitch {row_pitch} smaller than RGBA stride {tight_stride}"
        )
    if data_size > 0 and offset.value + image_size > data_size:
        raise _error(
            f"KTX2 level0 span out of range "
            f"(offset={offset.value}, size={image_size}, dataSize={data_size})"
        )

    level_addr = data_addr + int(offset.value)
    if row_pitch == tight_stride and image_size >= expected:
        rgba = bytes((c_ubyte * expected).from_address(level_addr))
        return width, height, rgba

    # Copy rows tightly when the transcoder pads row pitch.
    rows = bytearray(expected)
    src = (c_ubyte * image_size).from_address(level_addr)
    for row in range(height):
        start = row * row_pitch
        dest = row * tight_stride
        rows[dest : dest + tight_stride] = bytes(src[start : start + tight_stride])
    return width, height, bytes(rows)


def ktx2_bytes_to_png(ktx_bytes: bytes) -> bytes:
    """Decode a KTX2 (BasisU/UASTC) blob to PNG bytes."""
    if not ktx_bytes:
        raise _error("Empty KTX2 image")
    if not ktx_bytes.startswith(_KTX2_IDENTIFIER):
        raise _error("Not a KTX2 file (KTX1 / other formats unsupported)")

    lib = _load_library()
    texture_ptr = c_void_p()
    source = (c_ubyte * len(ktx_bytes)).from_buffer_copy(ktx_bytes)
    create = getattr(lib, "ktxTexture2_CreateFromMemory", None)
    if create is not None:
        result = create(
            source,
            len(ktx_bytes),
            _KTX_TEXTURE_CREATE_LOAD_IMAGE_DATA_BIT,
            byref(texture_ptr),
        )
        create_name = "ktxTexture2_CreateFromMemory"
    else:
        result = lib.ktxTexture_CreateFromMemory(
            source,
            len(ktx_bytes),
            _KTX_TEXTURE_CREATE_LOAD_IMAGE_DATA_BIT,
            byref(texture_ptr),
        )
        create_name = "ktxTexture_CreateFromMemory"
    if result != _KTX_SUCCESS or not texture_ptr.value:
        raise _ktx_error(lib, result, f"{create_name} failed")

    try:
        if lib.ktxTexture2_NeedsTranscoding(texture_ptr):
            tr = lib.ktxTexture2_TranscodeBasis(texture_ptr, _KTX_TTF_RGBA32, 0)
            if tr != _KTX_SUCCESS:
                raise _ktx_error(lib, tr, "ktxTexture2_TranscodeBasis failed")

        width, height, rgba = _level0_rgba32(lib, texture_ptr)
        return _encode_png_rgba(width, height, rgba)
    finally:
        lib.ktxTexture2_Destroy(texture_ptr)


def _image_is_ktx2(image: dict[str, Any]) -> bool:
    mime = str(image.get("mimeType") or "").lower()
    if mime == "image/ktx2":
        return True
    uri = str(image.get("uri") or "").lower()
    return uri.endswith(".ktx2")


def _lists_extension(gltf: dict[str, Any], name: str) -> bool:
    for key in ("extensionsRequired", "extensionsUsed"):
        values = gltf.get(key) or []
        if name in values:
            return True
    return False


def gltf_needs_ktx2_transcode(gltf: dict[str, Any]) -> bool:
    """Return True if GLTF uses BasisU/KTX2 textures F3D cannot load."""
    if _lists_extension(gltf, BASISU_EXTENSION):
        return True

    images = gltf.get("images") or []
    for image in images:
        if isinstance(image, dict) and _image_is_ktx2(image):
            return True

    for texture in gltf.get("textures") or []:
        if not isinstance(texture, dict):
            continue
        extensions = texture.get("extensions") or {}
        if BASISU_EXTENSION in extensions:
            return True
        source = texture.get("source")
        if isinstance(source, int) and 0 <= source < len(images):
            image = images[source]
            if isinstance(image, dict) and _image_is_ktx2(image):
                return True
    return False


def _view_bytes(
    gltf: dict[str, Any], bin_chunk: bytes, view_index: int
) -> bytes:
    views = gltf.get("bufferViews") or []
    if view_index < 0 or view_index >= len(views):
        raise _error(f"Invalid bufferView index for KTX2 image: {view_index}")
    view = views[view_index]
    if not isinstance(view, dict):
        raise _error(f"Invalid bufferView for KTX2 image: {view_index}")
    buffer_index = int(view.get("buffer", 0))
    if buffer_index != 0:
        raise _error(
            "KTX2 transcode supports self-contained .glb only "
            f"(bufferView {view_index} uses buffer {buffer_index})"
        )
    offset = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", 0))
    end = offset + length
    if offset < 0 or length < 0 or end > len(bin_chunk):
        raise _error(
            f"KTX2 bufferView {view_index} out of range "
            f"(offset={offset}, length={length}, bin={len(bin_chunk)})"
        )
    return bin_chunk[offset:end]


def _image_bytes(
    gltf: dict[str, Any], bin_chunk: bytes, image: dict[str, Any]
) -> bytes:
    if image.get("uri"):
        raise _error(
            "KTX2 transcode supports self-contained .glb only (image has uri)"
        )
    if "bufferView" not in image:
        raise _error("KTX2 image missing bufferView")
    return _view_bytes(gltf, bin_chunk, int(image["bufferView"]))


def _drop_texture_basisu(texture: dict[str, Any]) -> bool:
    extensions = texture.get("extensions")
    if not isinstance(extensions, dict) or BASISU_EXTENSION not in extensions:
        return False
    extensions.pop(BASISU_EXTENSION, None)
    if not extensions:
        texture.pop("extensions", None)
    return True


def transcode_ktx2_in_gltf(gltf: dict[str, Any], bin_chunk: bytes) -> bytes:
    """
    Rewrite textures using KHR_texture_basisu / KTX2 to PNG.

    Prefer existing PNG/JPEG ``texture.source`` fallbacks when present.
    Otherwise decode the BasisU/KTX2 source to PNG and point ``source`` at it.
    """
    from .meshopt_decompress import _align4, _append_bytes, _strip_extensions

    images = gltf.setdefault("images", [])
    textures = gltf.get("textures") or []
    views = gltf.setdefault("bufferViews", [])
    new_bin = bytearray(bin_chunk)
    changed = False

    for texture in textures:
        if not isinstance(texture, dict):
            continue

        extensions = texture.get("extensions") or {}
        basisu = extensions.get(BASISU_EXTENSION)
        basisu_source: int | None = None
        if isinstance(basisu, dict) and isinstance(basisu.get("source"), int):
            basisu_source = int(basisu["source"])

        fallback_source = texture.get("source")
        has_fallback = isinstance(fallback_source, int)

        if has_fallback and basisu_source is not None:
            # Keep PNG/JPEG fallback; drop BasisU pointer.
            if _drop_texture_basisu(texture):
                changed = True
            continue

        decode_index: int | None = None
        if basisu_source is not None:
            decode_index = basisu_source
        elif has_fallback:
            image = images[fallback_source]
            if isinstance(image, dict) and _image_is_ktx2(image):
                decode_index = int(fallback_source)

        if decode_index is None:
            if _drop_texture_basisu(texture):
                changed = True
            continue

        if decode_index < 0 or decode_index >= len(images):
            raise _error(f"Invalid KTX2 image index: {decode_index}")

        image = images[decode_index]
        if not isinstance(image, dict):
            raise _error(f"Invalid image entry: {decode_index}")

        ktx_bytes = _image_bytes(gltf, bin_chunk, image)
        png_bytes = ktx2_bytes_to_png(ktx_bytes)

        offset = _append_bytes(new_bin, png_bytes)
        view_index = len(views)
        views.append(
            {
                "buffer": 0,
                "byteOffset": offset,
                "byteLength": len(png_bytes),
            }
        )

        replacement: dict[str, Any] = {
            "mimeType": "image/png",
            "bufferView": view_index,
        }
        if "name" in image:
            replacement["name"] = image["name"]
        images[decode_index] = replacement
        texture["source"] = decode_index
        _drop_texture_basisu(texture)
        changed = True

    if not changed and not _lists_extension(gltf, BASISU_EXTENSION):
        return bin_chunk

    # Pad and publish new BIN length on buffer 0.
    pad = _align4(len(new_bin)) - len(new_bin)
    if pad:
        new_bin.extend(b"\x00" * pad)

    buffers = gltf.get("buffers")
    if not buffers:
        gltf["buffers"] = [{"byteLength": len(new_bin)}]
    else:
        buffer0 = buffers[0]
        if isinstance(buffer0, dict):
            buffer0["byteLength"] = len(new_bin)
        else:
            buffers[0] = {"byteLength": len(new_bin)}

    _strip_extensions(gltf, (BASISU_EXTENSION,))
    return bytes(new_bin)
