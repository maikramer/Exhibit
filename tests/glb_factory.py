# SPDX-License-Identifier: GPL-3.0-or-later
"""Build tiny synthetic GLBs for unit tests (no external assets)."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942


def glb_bytes(gltf: dict[str, Any], bin_chunk: bytes = b"") -> bytes:
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_padding = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b" " * json_padding
    bin_padding = (4 - (len(bin_chunk) % 4)) % 4
    bin_bytes = bin_chunk + (b"\x00" * bin_padding)
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    return b"".join(
        (
            struct.pack("<III", _GLB_MAGIC, 2, total),
            struct.pack("<II", len(json_bytes), _CHUNK_JSON),
            json_bytes,
            struct.pack("<II", len(bin_bytes), _CHUNK_BIN),
            bin_bytes,
        )
    )


def write_glb(path: Path, gltf: dict[str, Any], bin_chunk: bytes = b"") -> Path:
    path.write_bytes(glb_bytes(gltf, bin_chunk))
    return path


def triangle_positions() -> bytes:
    # Three VEC3 floats: (0,0,0), (1,0,0), (0,2,0) — height 2 on +Y.
    return struct.pack(
        "<9f",
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        2.0,
        0.0,
    )


def triangle_indices() -> bytes:
    return struct.pack("<3H", 0, 1, 2)


def plain_triangle_gltf() -> tuple[dict[str, Any], bytes]:
    positions = triangle_positions()
    indices = triangle_indices()
    # Pack indices then positions (align4).
    idx_pad = (4 - (len(indices) % 4)) % 4
    bin_chunk = indices + (b"\x00" * idx_pad) + positions
    pos_offset = len(indices) + idx_pad
    gltf: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Tri", "mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 1},
                        "indices": 0,
                        "mode": 4,
                    }
                ]
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5123,
                "count": 3,
                "type": "SCALAR",
                "max": [2],
                "min": [0],
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "max": [1.0, 2.0, 0.0],
                "min": [0.0, 0.0, 0.0],
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(indices)},
            {
                "buffer": 0,
                "byteOffset": pos_offset,
                "byteLength": len(positions),
            },
        ],
        "buffers": [{"byteLength": len(bin_chunk)}],
    }
    return gltf, bin_chunk


def multipart_gltf() -> tuple[dict[str, Any], bytes]:
    """Root with two mesh children (for hide-nodes tests)."""
    gltf, bin_chunk = plain_triangle_gltf()
    gltf["nodes"] = [
        {"name": "Root", "children": [1, 2]},
        {"name": "PartA", "mesh": 0},
        {"name": "PartB", "mesh": 0},
    ]
    gltf["scenes"] = [{"nodes": [0]}]
    return gltf, bin_chunk


def quantized_triangle_gltf() -> tuple[dict[str, Any], bytes]:
    """UNSIGNED_BYTE positions + KHR_mesh_quantization (no meshopt)."""
    # 3 VEC3 u8 positions: (0,0,0), (255,0,0), (0,255,0) normalized → ~unit.
    positions = struct.pack("<9B", 0, 0, 0, 255, 0, 0, 0, 255, 0)
    indices = triangle_indices()
    idx_pad = (4 - (len(indices) % 4)) % 4
    bin_chunk = indices + (b"\x00" * idx_pad) + positions
    pos_offset = len(indices) + idx_pad
    gltf: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "extensionsUsed": ["KHR_mesh_quantization"],
        "extensionsRequired": ["KHR_mesh_quantization"],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "QTri", "mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 1},
                        "indices": 0,
                        "mode": 4,
                    }
                ]
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5123,
                "count": 3,
                "type": "SCALAR",
                "max": [2],
                "min": [0],
            },
            {
                "bufferView": 1,
                "componentType": 5121,
                "normalized": True,
                "count": 3,
                "type": "VEC3",
                "max": [1.0, 1.0, 0.0],
                "min": [0.0, 0.0, 0.0],
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(indices)},
            {
                "buffer": 0,
                "byteOffset": pos_offset,
                "byteLength": len(positions),
            },
        ],
        "buffers": [{"byteLength": len(bin_chunk)}],
    }
    return gltf, bin_chunk


def basisu_fallback_gltf() -> tuple[dict[str, Any], bytes]:
    """KHR_texture_basisu with PNG source fallback (no libktx needed)."""
    from exhibit.ktx2_transcode import _encode_png_rgba

    gltf, bin_chunk = plain_triangle_gltf()
    png = _encode_png_rgba(1, 1, bytes([255, 0, 0, 255]))
    # Append PNG after existing BIN payload.
    from exhibit.meshopt_decompress import _align4

    pad = _align4(len(bin_chunk)) - len(bin_chunk)
    bin_chunk = bin_chunk + (b"\x00" * pad) + png
    png_offset = len(bin_chunk) - len(png)
    png_view = len(gltf["bufferViews"])
    gltf["bufferViews"].append(
        {"buffer": 0, "byteOffset": png_offset, "byteLength": len(png)}
    )
    gltf["buffers"][0]["byteLength"] = len(bin_chunk)
    gltf["extensionsUsed"] = ["KHR_texture_basisu"]
    gltf["images"] = [
        {"mimeType": "image/png", "bufferView": png_view},
        {"mimeType": "image/ktx2", "bufferView": png_view},
    ]
    gltf["textures"] = [
        {
            "source": 0,
            "extensions": {"KHR_texture_basisu": {"source": 1}},
        }
    ]
    gltf["materials"] = [
        {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
    ]
    gltf["meshes"][0]["primitives"][0]["material"] = 0
    return gltf, bin_chunk


def non_indexed_triangle_gltf() -> tuple[dict[str, Any], bytes]:
    """Three vertices, no indices (faces = verts // 3)."""
    positions = triangle_positions()
    gltf: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "NI", "mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0}, "mode": 4}
                ]
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "max": [1.0, 2.0, 0.0],
                "min": [0.0, 0.0, 0.0],
            }
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}
        ],
        "buffers": [{"byteLength": len(positions)}],
    }
    return gltf, positions


def translated_triangle_gltf(
    translation: list[float],
) -> tuple[dict[str, Any], bytes]:
    """Plain triangle with node translation (for world-AABB height tests)."""
    gltf, bin_chunk = plain_triangle_gltf()
    gltf["nodes"][0]["translation"] = list(translation)
    return gltf, bin_chunk


def scaled_triangle_gltf(scale: list[float]) -> tuple[dict[str, Any], bytes]:
    gltf, bin_chunk = plain_triangle_gltf()
    gltf["nodes"][0]["scale"] = list(scale)
    return gltf, bin_chunk


def empty_scene_gltf() -> tuple[dict[str, Any], bytes]:
    """Valid GLB with nodes but no meshes."""
    gltf: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Empty"}],
        "buffers": [{"byteLength": 0}],
    }
    return gltf, b""
