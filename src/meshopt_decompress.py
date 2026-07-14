# meshopt_decompress.py
#
# Copyright 2024-2025 Nokse <nokse@posteo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Decompress GLBs that use EXT/KHR_meshopt_compression before F3D/VTK load."""

from __future__ import annotations

import json
import os
import struct
import tempfile
from ctypes import (
    CDLL,
    POINTER,
    c_int,
    c_size_t,
    c_ubyte,
    c_void_p,
    cast,
)
from ctypes.util import find_library
from typing import Any

MESHOPT_EXTENSIONS = (
    "EXT_meshopt_compression",
    "KHR_meshopt_compression",
)

_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942

_lib: CDLL | None = None
_lib_failed = False


class MeshoptError(Exception):
    """Raised when a meshopt-compressed GLB cannot be decompressed."""


def _load_library() -> CDLL:
    global _lib, _lib_failed
    if _lib is not None:
        return _lib
    if _lib_failed:
        raise MeshoptError("libmeshoptimizer is not available")

    candidates = [
        "meshoptimizer",
        "libmeshoptimizer.so",
        "/app/lib/libmeshoptimizer.so",
        "/usr/lib/libmeshoptimizer.so",
        "/usr/local/lib/libmeshoptimizer.so",
    ]
    found = find_library("meshoptimizer")
    if found:
        candidates.insert(0, found)

    last_error: Exception | None = None
    for name in candidates:
        try:
            lib = CDLL(name)
        except OSError as exc:
            last_error = exc
            continue
        _configure_lib(lib)
        _lib = lib
        return lib

    _lib_failed = True
    raise MeshoptError(
        "libmeshoptimizer is not available; cannot open meshopt-compressed GLB"
    ) from last_error


def _configure_lib(lib: CDLL) -> None:
    lib.meshopt_decodeVertexBuffer.argtypes = [
        c_void_p,
        c_size_t,
        c_size_t,
        POINTER(c_ubyte),
        c_size_t,
    ]
    lib.meshopt_decodeVertexBuffer.restype = c_int

    lib.meshopt_decodeIndexBuffer.argtypes = [
        c_void_p,
        c_size_t,
        c_size_t,
        POINTER(c_ubyte),
        c_size_t,
    ]
    lib.meshopt_decodeIndexBuffer.restype = c_int

    lib.meshopt_decodeIndexSequence.argtypes = [
        c_void_p,
        c_size_t,
        c_size_t,
        POINTER(c_ubyte),
        c_size_t,
    ]
    lib.meshopt_decodeIndexSequence.restype = c_int

    for filter_name in (
        "meshopt_decodeFilterOct",
        "meshopt_decodeFilterQuat",
        "meshopt_decodeFilterExp",
        "meshopt_decodeFilterColor",
    ):
        fn = getattr(lib, filter_name)
        fn.argtypes = [c_void_p, c_size_t, c_size_t]
        fn.restype = None


def _read_glb(path: str) -> tuple[dict[str, Any], bytes]:
    with open(path, "rb") as handle:
        data = handle.read()

    if len(data) < 12:
        raise MeshoptError(f"File too small to be a GLB: {path}")

    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != _GLB_MAGIC:
        raise MeshoptError(f"Not a GLB file: {path}")
    if version != 2:
        raise MeshoptError(f"Unsupported GLB version {version}: {path}")
    if length > len(data):
        raise MeshoptError(f"Truncated GLB: {path}")

    offset = 12
    json_chunk: bytes | None = None
    bin_chunk = b""

    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk_data = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == _CHUNK_JSON:
            json_chunk = chunk_data
        elif chunk_type == _CHUNK_BIN:
            bin_chunk = chunk_data

    if json_chunk is None:
        raise MeshoptError(f"GLB missing JSON chunk: {path}")

    try:
        gltf = json.loads(json_chunk.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MeshoptError(f"Invalid GLB JSON chunk: {path}") from exc

    return gltf, bin_chunk


def _write_glb(path: str, gltf: dict[str, Any], bin_chunk: bytes) -> None:
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_padding = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b" " * json_padding

    bin_padding = (4 - (len(bin_chunk) % 4)) % 4
    bin_bytes = bin_chunk + (b"\x00" * bin_padding)

    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<III", _GLB_MAGIC, 2, total))
        handle.write(struct.pack("<II", len(json_bytes), _CHUNK_JSON))
        handle.write(json_bytes)
        handle.write(struct.pack("<II", len(bin_bytes), _CHUNK_BIN))
        handle.write(bin_bytes)


def _extension_on_view(view: dict[str, Any]) -> dict[str, Any] | None:
    extensions = view.get("extensions") or {}
    for name in MESHOPT_EXTENSIONS:
        ext = extensions.get(name)
        if isinstance(ext, dict):
            return ext
    return None


def _is_fallback_buffer(buffer_def: dict[str, Any]) -> bool:
    extensions = buffer_def.get("extensions") or {}
    for name in MESHOPT_EXTENSIONS:
        ext = extensions.get(name)
        if isinstance(ext, dict) and ext.get("fallback"):
            return True
    return False


def needs_meshopt_decompress(path: str) -> bool:
    """Return True if path is a GLB that uses meshopt bufferView compression."""
    if not path or not str(path).lower().endswith(".glb"):
        return False
    try:
        gltf, _bin = _read_glb(path)
    except (OSError, MeshoptError):
        return False

    for view in gltf.get("bufferViews") or []:
        if _extension_on_view(view):
            return True

    required = gltf.get("extensionsRequired") or []
    return any(name in required for name in MESHOPT_EXTENSIONS)


def _buffer_payloads(gltf: dict[str, Any], bin_chunk: bytes) -> list[bytes | None]:
    buffers = gltf.get("buffers") or []
    payloads: list[bytes | None] = []
    for index, buffer_def in enumerate(buffers):
        if _is_fallback_buffer(buffer_def):
            payloads.append(None)
            continue
        uri = buffer_def.get("uri")
        if uri:
            raise MeshoptError(
                "meshopt decompress supports self-contained .glb only "
                f"(buffer {index} has uri)"
            )
        # GLB binary chunk is buffer 0 when uri is omitted.
        if index == 0:
            payloads.append(bin_chunk)
        else:
            # Placeholder buffer without fallback flag and without uri.
            payloads.append(None)
    return payloads


def _decode_view(lib: CDLL, source: bytes, ext: dict[str, Any]) -> bytes:
    mode = ext.get("mode")
    filter_name = ext.get("filter") or "NONE"
    count = int(ext["count"])
    stride = int(ext["byteStride"])
    if count < 0 or stride <= 0:
        raise MeshoptError("Invalid meshopt bufferView parameters")

    destination = (c_ubyte * (count * stride))()
    source_buf = (c_ubyte * len(source)).from_buffer_copy(source)

    decoders = {
        "ATTRIBUTES": lib.meshopt_decodeVertexBuffer,
        "TRIANGLES": lib.meshopt_decodeIndexBuffer,
        "INDICES": lib.meshopt_decodeIndexSequence,
    }
    decode_fn = decoders.get(mode)
    if decode_fn is None:
        raise MeshoptError(f"Unsupported meshopt mode: {mode}")

    result = decode_fn(destination, count, stride, source_buf, len(source))
    if result != 0:
        raise MeshoptError(f"meshopt decode failed (mode={mode}, code={result})")

    filters = {
        "NONE": None,
        "OCTAHEDRAL": lib.meshopt_decodeFilterOct,
        "QUATERNION": lib.meshopt_decodeFilterQuat,
        "EXPONENTIAL": lib.meshopt_decodeFilterExp,
        "COLOR": lib.meshopt_decodeFilterColor,
    }
    if filter_name not in filters:
        raise MeshoptError(f"Unsupported meshopt filter: {filter_name}")

    filter_fn = filters[filter_name]
    if filter_fn is not None:
        # Match meshoptimizer JS decoder: round count up to multiple of 4.
        count4 = (count + 3) & ~3
        filter_fn(cast(destination, c_void_p), count4, stride)

    return bytes(destination)


def _align4(value: int) -> int:
    return (value + 3) & ~3


def decompress_glb(path: str) -> str:
    """
    Return a path to a GLB without meshopt compression.

    If decompression is unnecessary, returns ``path``. Otherwise writes a
    temporary ``.glb`` and returns that path. Caller should delete temps via
    ``cleanup_decompressed``.
    """
    if not needs_meshopt_decompress(path):
        return path

    lib = _load_library()
    gltf, bin_chunk = _read_glb(path)
    payloads = _buffer_payloads(gltf, bin_chunk)

    new_bin = bytearray()
    new_views: list[dict[str, Any]] = []

    for view in gltf.get("bufferViews") or []:
        ext = _extension_on_view(view)
        if ext is not None:
            src_buffer = int(ext["buffer"])
            src_offset = int(ext.get("byteOffset") or 0)
            src_length = int(ext["byteLength"])
            payload = payloads[src_buffer] if 0 <= src_buffer < len(payloads) else None
            if payload is None:
                raise MeshoptError(
                    f"Missing compressed buffer data for buffer {src_buffer}"
                )
            source = payload[src_offset : src_offset + src_length]
            if len(source) != src_length:
                raise MeshoptError("Compressed bufferView data is truncated")
            decoded = _decode_view(lib, source, ext)
        else:
            src_buffer = int(view.get("buffer", 0))
            src_offset = int(view.get("byteOffset") or 0)
            src_length = int(view["byteLength"])
            payload = payloads[src_buffer] if 0 <= src_buffer < len(payloads) else None
            if payload is None:
                raise MeshoptError(
                    f"Missing buffer data for uncompressed bufferView "
                    f"(buffer {src_buffer})"
                )
            decoded = payload[src_offset : src_offset + src_length]
            if len(decoded) != src_length:
                raise MeshoptError("Uncompressed bufferView data is truncated")

        padding = _align4(len(new_bin)) - len(new_bin)
        if padding:
            new_bin.extend(b"\x00" * padding)

        new_view = {
            key: value
            for key, value in view.items()
            if key not in ("buffer", "byteOffset", "byteLength", "extensions")
        }
        new_view["buffer"] = 0
        new_view["byteOffset"] = len(new_bin)
        new_view["byteLength"] = len(decoded)

        # Preserve parent extensions except meshopt.
        old_ext = view.get("extensions")
        if old_ext:
            kept = {
                name: value
                for name, value in old_ext.items()
                if name not in MESHOPT_EXTENSIONS
            }
            if kept:
                new_view["extensions"] = kept

        new_bin.extend(decoded)
        new_views.append(new_view)

    gltf["bufferViews"] = new_views
    gltf["buffers"] = [{"byteLength": len(new_bin)}]

    for key in ("extensionsUsed", "extensionsRequired"):
        values = gltf.get(key)
        if not values:
            continue
        filtered = [name for name in values if name not in MESHOPT_EXTENSIONS]
        if filtered:
            gltf[key] = filtered
        else:
            del gltf[key]

    # Drop top-level meshopt extension objects if present.
    top_ext = gltf.get("extensions")
    if top_ext:
        for name in MESHOPT_EXTENSIONS:
            top_ext.pop(name, None)
        if not top_ext:
            del gltf["extensions"]

    fd, temp_path = tempfile.mkstemp(prefix="exhibit-meshopt-", suffix=".glb")
    os.close(fd)
    try:
        _write_glb(temp_path, gltf, bytes(new_bin))
    except Exception:
        cleanup_decompressed(temp_path)
        raise
    return temp_path


def cleanup_decompressed(path: str | None) -> None:
    """Delete a temporary GLB created by ``decompress_glb``."""
    if not path:
        return
    try:
        if os.path.basename(path).startswith("exhibit-meshopt-"):
            os.unlink(path)
    except OSError:
        pass


def prepare_glb_for_load(path: str) -> tuple[str, str | None]:
    """
    Prepare a path for F3D.

    Returns ``(load_path, temp_path)``. ``temp_path`` is set when a temporary
    decompressed file was created and must be cleaned up by the caller.
    """
    if not needs_meshopt_decompress(path):
        return path, None
    load_path = decompress_glb(path)
    if load_path == path:
        return path, None
    return load_path, load_path
