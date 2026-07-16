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

"""Prepare GLBs for F3D/VTK by expanding meshopt + KHR_mesh_quantization."""

from __future__ import annotations

import json
import math
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
QUANTIZATION_EXTENSION = "KHR_mesh_quantization"

_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942

_COMPONENT_SIZE = {
    5120: 1,  # BYTE
    5121: 1,  # UNSIGNED_BYTE
    5122: 2,  # SHORT
    5123: 2,  # UNSIGNED_SHORT
    5125: 4,  # UNSIGNED_INT
    5126: 4,  # FLOAT
}
_COMPONENT_STRUCT = {
    5120: "b",
    5121: "B",
    5122: "h",
    5123: "H",
    5125: "I",
    5126: "f",
}
_TYPE_COUNT = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}
_FLOAT = 5126

_lib: CDLL | None = None
_lib_failed = False

# Prepared GLB cache: (realpath, mtime_ns, size) → temp path owned by this module.
_prepare_cache: dict[tuple[str, int, int], str] = {}
_prepare_cache_by_abs: dict[str, tuple[tuple[str, int, int], str]] = {}


class MeshoptError(Exception):
    """Raised when a GLB cannot be prepared for load."""


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
        fn = getattr(lib, filter_name, None)
        if fn is None:
            continue
        fn.argtypes = [c_void_p, c_size_t, c_size_t]
        fn.restype = None


def _parse_glb_header(header: bytes, path: str) -> tuple[int, int]:
    if len(header) < 12:
        raise MeshoptError(f"File too small to be a GLB: {path}")
    magic, version, length = struct.unpack_from("<III", header, 0)
    if magic != _GLB_MAGIC:
        raise MeshoptError(f"Not a GLB file: {path}")
    if version != 2:
        raise MeshoptError(f"Unsupported GLB version {version}: {path}")
    return version, length


def _decode_gltf_json(json_chunk: bytes, path: str) -> dict[str, Any]:
    try:
        gltf = json.loads(json_chunk.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MeshoptError(f"Invalid GLB JSON chunk: {path}") from exc
    if not isinstance(gltf, dict):
        raise MeshoptError(f"Invalid GLB JSON root: {path}")
    return gltf


def _read_glb_json(path: str) -> dict[str, Any]:
    """Read only the JSON chunk of a GLB (skip BIN payload)."""
    with open(path, "rb") as handle:
        header = handle.read(12)
        _parse_glb_header(header, path)

        while True:
            chunk_header = handle.read(8)
            if len(chunk_header) < 8:
                break
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            if chunk_type == _CHUNK_JSON:
                json_chunk = handle.read(chunk_length)
                if len(json_chunk) < chunk_length:
                    raise MeshoptError(f"Truncated GLB JSON chunk: {path}")
                return _decode_gltf_json(json_chunk, path)
            # Skip non-JSON chunks without loading them into memory.
            handle.seek(chunk_length, os.SEEK_CUR)

    raise MeshoptError(f"GLB missing JSON chunk: {path}")


def _read_glb(path: str) -> tuple[dict[str, Any], bytes]:
    with open(path, "rb") as handle:
        data = handle.read()

    _parse_glb_header(data[:12], path)
    _magic, _version, length = struct.unpack_from("<III", data, 0)
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

    return _decode_gltf_json(json_chunk, path), bin_chunk


def _file_cache_key(path: str) -> tuple[str, int, int]:
    abs_path = os.path.realpath(path)
    stat = os.stat(abs_path)
    return abs_path, int(stat.st_mtime_ns), int(stat.st_size)


def _cache_prepared(key: tuple[str, int, int], temp_path: str) -> None:
    abs_path = key[0]
    previous = _prepare_cache_by_abs.get(abs_path)
    if previous is not None:
        prev_key, prev_temp = previous
        _prepare_cache.pop(prev_key, None)
        if prev_temp != temp_path:
            try:
                os.unlink(prev_temp)
            except OSError:
                pass
    _prepare_cache[key] = temp_path
    _prepare_cache_by_abs[abs_path] = (key, temp_path)


def _cached_prepared(key: tuple[str, int, int]) -> str | None:
    cached = _prepare_cache.get(key)
    if cached and os.path.isfile(cached):
        return cached
    if cached:
        _prepare_cache.pop(key, None)
        abs_path = key[0]
        entry = _prepare_cache_by_abs.get(abs_path)
        if entry and entry[0] == key:
            _prepare_cache_by_abs.pop(abs_path, None)
    return None


def clear_prepare_cache() -> None:
    """Delete all cached prepared GLBs (tests / shutdown)."""
    for temp_path in list(_prepare_cache.values()):
        try:
            os.unlink(temp_path)
        except OSError:
            pass
    _prepare_cache.clear()
    _prepare_cache_by_abs.clear()


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


def _lists_extension(gltf: dict[str, Any], name: str) -> bool:
    for key in ("extensionsRequired", "extensionsUsed"):
        values = gltf.get(key) or []
        if name in values:
            return True
    return False


def _gltf_has_meshopt(gltf: dict[str, Any]) -> bool:
    for view in gltf.get("bufferViews") or []:
        if _extension_on_view(view):
            return True
    return any(_lists_extension(gltf, name) for name in MESHOPT_EXTENSIONS)


def _gltf_has_quantization(gltf: dict[str, Any]) -> bool:
    return _lists_extension(gltf, QUANTIZATION_EXTENSION)


def needs_meshopt_decompress(path: str) -> bool:
    """Return True if path is a GLB that needs meshopt and/or dequantization."""
    if not path or not str(path).lower().endswith(".glb"):
        return False
    try:
        gltf = _read_glb_json(path)
    except (OSError, MeshoptError):
        return False
    return _gltf_has_meshopt(gltf) or _gltf_has_quantization(gltf)


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

    # meshopt filters process vertices in groups of 4 and may write past
    # ``count`` up to the next multiple of 4 — allocate that pad.
    count4 = (count + 3) & ~3
    alloc_count = count4 if filter_name != "NONE" else count
    destination = (c_ubyte * (alloc_count * stride))()
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
        "OCTAHEDRAL": getattr(lib, "meshopt_decodeFilterOct", None),
        "QUATERNION": getattr(lib, "meshopt_decodeFilterQuat", None),
        "EXPONENTIAL": getattr(lib, "meshopt_decodeFilterExp", None),
        "COLOR": getattr(lib, "meshopt_decodeFilterColor", None),
    }
    if filter_name not in filters:
        raise MeshoptError(f"Unsupported meshopt filter: {filter_name}")

    filter_fn = filters[filter_name]
    if filter_name != "NONE" and filter_fn is None:
        raise MeshoptError(
            f"meshopt filter {filter_name} is not available in libmeshoptimizer"
        )
    if filter_fn is not None:
        filter_fn(cast(destination, c_void_p), count4, stride)

    return bytes(destination)[: count * stride]


def _align4(value: int) -> int:
    return (value + 3) & ~3


def _append_bytes(dest: bytearray, payload: bytes) -> int:
    padding = _align4(len(dest)) - len(dest)
    if padding:
        dest.extend(b"\x00" * padding)
    offset = len(dest)
    dest.extend(payload)
    return offset


def _strip_extensions(gltf: dict[str, Any], names: tuple[str, ...] | list[str]) -> None:
    drop = set(names)
    for key in ("extensionsUsed", "extensionsRequired"):
        values = gltf.get(key)
        if not values:
            continue
        filtered = [name for name in values if name not in drop]
        if filtered:
            gltf[key] = filtered
        else:
            del gltf[key]

    top_ext = gltf.get("extensions")
    if top_ext:
        for name in drop:
            top_ext.pop(name, None)
        if not top_ext:
            del gltf["extensions"]


def _decompress_meshopt(gltf: dict[str, Any], bin_chunk: bytes) -> bytes:
    lib = _load_library()
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

        new_view = {
            key: value
            for key, value in view.items()
            if key not in ("buffer", "byteOffset", "byteLength", "extensions")
        }
        new_view["buffer"] = 0
        new_view["byteOffset"] = _append_bytes(new_bin, decoded)
        new_view["byteLength"] = len(decoded)

        old_ext = view.get("extensions")
        if old_ext:
            kept = {
                name: value
                for name, value in old_ext.items()
                if name not in MESHOPT_EXTENSIONS
            }
            if kept:
                new_view["extensions"] = kept

        new_views.append(new_view)

    gltf["bufferViews"] = new_views
    gltf["buffers"] = [{"byteLength": len(new_bin)}]
    _strip_extensions(gltf, MESHOPT_EXTENSIONS)
    return bytes(new_bin)


def _should_dequant_attr(name: str) -> bool:
    if name in ("POSITION", "NORMAL", "TANGENT"):
        return True
    return name.startswith("TEXCOORD_")


def _collect_dequant_accessors(gltf: dict[str, Any]) -> set[int]:
    result: set[int] = set()
    for mesh in gltf.get("meshes") or []:
        for prim in mesh.get("primitives") or []:
            for name, accessor_index in (prim.get("attributes") or {}).items():
                if _should_dequant_attr(name):
                    result.add(int(accessor_index))
            for target in prim.get("targets") or []:
                for name, accessor_index in target.items():
                    if _should_dequant_attr(name):
                        result.add(int(accessor_index))
    return result


def _dequant_scalar(value: int | float, component_type: int, normalized: bool) -> float:
    if component_type == _FLOAT:
        return float(value)
    ivalue = int(value)
    if not normalized:
        return float(ivalue)
    if component_type == 5120:
        return max(ivalue / 127.0, -1.0)
    if component_type == 5121:
        return ivalue / 255.0
    if component_type == 5122:
        return max(ivalue / 32767.0, -1.0)
    if component_type == 5123:
        return ivalue / 65535.0
    raise MeshoptError(
        f"Unsupported quantized componentType for dequantization: {component_type}"
    )


def _accessor_stride(accessor: dict[str, Any], view: dict[str, Any]) -> int:
    component_type = int(accessor["componentType"])
    type_name = accessor["type"]
    if type_name not in _TYPE_COUNT or component_type not in _COMPONENT_SIZE:
        raise MeshoptError("Unsupported accessor type for dequantization")
    default = _TYPE_COUNT[type_name] * _COMPONENT_SIZE[component_type]
    stride = view.get("byteStride")
    if stride is None:
        return default
    stride_i = int(stride)
    if stride_i < default:
        raise MeshoptError("Invalid accessor byteStride")
    return stride_i


def _read_accessor_floats(
    gltf: dict[str, Any], bin_chunk: bytes, accessor: dict[str, Any]
) -> list[float]:
    if "bufferView" not in accessor:
        raise MeshoptError("Sparse-only accessors are not supported for dequantization")

    view = (gltf.get("bufferViews") or [])[int(accessor["bufferView"])]
    component_type = int(accessor["componentType"])
    type_name = accessor["type"]
    count = int(accessor["count"])
    normalized = bool(accessor.get("normalized"))
    ncomp = _TYPE_COUNT[type_name]
    fmt = _COMPONENT_STRUCT[component_type]
    stride = _accessor_stride(accessor, view)
    base = int(view.get("byteOffset") or 0) + int(accessor.get("byteOffset") or 0)

    values: list[float] = []
    for index in range(count):
        offset = base + index * stride
        comps = struct.unpack_from("<" + fmt * ncomp, bin_chunk, offset)
        for comp in comps:
            values.append(_dequant_scalar(comp, component_type, normalized))
    return values


def _copy_view_bytes(view: dict[str, Any], bin_chunk: bytes) -> bytes:
    src_offset = int(view.get("byteOffset") or 0)
    src_length = int(view["byteLength"])
    payload = bin_chunk[src_offset : src_offset + src_length]
    if len(payload) != src_length:
        raise MeshoptError("bufferView data is truncated")
    return payload


def _dequant_mesh_quantization(gltf: dict[str, Any], bin_chunk: bytes) -> bytes:
    accessors = gltf.get("accessors") or []
    buffer_views = gltf.get("bufferViews") or []
    dequant_accessors = {
        index
        for index in _collect_dequant_accessors(gltf)
        if 0 <= index < len(accessors)
        and int(accessors[index].get("componentType", _FLOAT)) != _FLOAT
    }

    if not dequant_accessors and not _gltf_has_quantization(gltf):
        return bin_chunk

    raw_views: set[int] = set()
    for image in gltf.get("images") or []:
        if "bufferView" in image:
            raw_views.add(int(image["bufferView"]))
    for index, accessor in enumerate(accessors):
        if index in dequant_accessors:
            continue
        if "bufferView" in accessor:
            raw_views.add(int(accessor["bufferView"]))

    new_bin = bytearray()
    new_views: list[dict[str, Any]] = []
    view_remap: dict[int, int] = {}

    for old_index in sorted(raw_views):
        if old_index < 0 or old_index >= len(buffer_views):
            raise MeshoptError(f"Invalid bufferView index {old_index}")
        old_view = buffer_views[old_index]
        payload = _copy_view_bytes(old_view, bin_chunk)
        new_view = {
            key: value
            for key, value in old_view.items()
            if key not in ("buffer", "byteOffset", "byteLength")
        }
        new_view["buffer"] = 0
        new_view["byteOffset"] = _append_bytes(new_bin, payload)
        new_view["byteLength"] = len(payload)
        view_remap[old_index] = len(new_views)
        new_views.append(new_view)

    for image in gltf.get("images") or []:
        if "bufferView" in image:
            image["bufferView"] = view_remap[int(image["bufferView"])]

    for index, accessor in enumerate(accessors):
        if index in dequant_accessors:
            continue
        if "bufferView" not in accessor:
            continue
        accessor["bufferView"] = view_remap[int(accessor["bufferView"])]

    for index in sorted(dequant_accessors):
        accessor = accessors[index]
        floats = _read_accessor_floats(gltf, bin_chunk, accessor)
        payload = struct.pack("<" + "f" * len(floats), *floats)
        ncomp = _TYPE_COUNT[accessor["type"]]

        new_view = {
            "buffer": 0,
            "byteOffset": _append_bytes(new_bin, payload),
            "byteLength": len(payload),
            "byteStride": ncomp * 4,
            "target": 34962,  # ARRAY_BUFFER
        }
        # Preserve target from old view when present.
        old_view_index = int(accessor["bufferView"])
        if 0 <= old_view_index < len(buffer_views):
            old_target = buffer_views[old_view_index].get("target")
            if old_target is not None:
                new_view["target"] = old_target

        accessor["bufferView"] = len(new_views)
        accessor["byteOffset"] = 0
        accessor["componentType"] = _FLOAT
        accessor.pop("normalized", None)

        # min/max in quantized files are in the quantized domain; rewrite from floats.
        if floats and ("min" in accessor or "max" in accessor):
            mins = [math.inf] * ncomp
            maxs = [-math.inf] * ncomp
            for row in range(int(accessor["count"])):
                base = row * ncomp
                for comp_i in range(ncomp):
                    value = floats[base + comp_i]
                    if value < mins[comp_i]:
                        mins[comp_i] = value
                    if value > maxs[comp_i]:
                        maxs[comp_i] = value
            if "min" in accessor:
                accessor["min"] = mins
            if "max" in accessor:
                accessor["max"] = maxs

        new_views.append(new_view)

    gltf["bufferViews"] = new_views
    gltf["buffers"] = [{"byteLength": len(new_bin)}]
    _strip_extensions(gltf, (QUANTIZATION_EXTENSION,))
    return bytes(new_bin)


def decompress_glb(path: str) -> str:
    """
    Return a path to a GLB without meshopt compression / mesh quantization.

    If preparation is unnecessary, returns ``path``. Otherwise writes a
    temporary ``.glb`` and returns that path. Prefer ``prepare_glb_for_load``,
    which caches prepared temps.
    """
    if not needs_meshopt_decompress(path):
        return path

    gltf, bin_chunk = _read_glb(path)
    changed = False

    if _gltf_has_meshopt(gltf):
        bin_chunk = _decompress_meshopt(gltf, bin_chunk)
        changed = True

    if _gltf_has_quantization(gltf):
        bin_chunk = _dequant_mesh_quantization(gltf, bin_chunk)
        changed = True

    if not changed:
        return path

    fd, temp_path = tempfile.mkstemp(prefix="exhibit-meshopt-", suffix=".glb")
    os.close(fd)
    try:
        _write_glb(temp_path, gltf, bin_chunk)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return temp_path


def cleanup_decompressed(path: str | None) -> None:
    """Delete a temporary GLB created by ``decompress_glb`` (not cache-owned)."""
    if not path:
        return
    # Cached prepared files are owned by the prepare cache.
    if path in _prepare_cache.values():
        return
    try:
        if os.path.basename(path).startswith("exhibit-meshopt-"):
            os.unlink(path)
    except OSError:
        pass


def prepare_glb_for_load(path: str) -> tuple[str, str | None]:
    """
    Prepare a path for F3D.

    Returns ``(load_path, temp_path)``. Prepared meshopt temps are owned by an
    internal cache keyed by ``(realpath, mtime, size)``; ``temp_path`` is then
    ``None`` and callers must not delete ``load_path``. Legacy callers that
    still receive a ``temp_path`` should call ``cleanup_decompressed``.
    """
    if not path or not str(path).lower().endswith(".glb"):
        return path, None

    try:
        key = _file_cache_key(path)
    except OSError:
        return path, None

    cached = _cached_prepared(key)
    if cached is not None:
        return cached, None

    if not needs_meshopt_decompress(path):
        return path, None

    load_path = decompress_glb(path)
    if load_path == path:
        return path, None

    _cache_prepared(key, load_path)
    return load_path, None
