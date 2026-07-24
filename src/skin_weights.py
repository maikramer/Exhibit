# SPDX-License-Identifier: GPL-3.0-or-later
"""glTF skin-weight helpers for F3D scivis / joint heat maps."""

from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass
from typing import Any

from .meshopt_decompress import (
    MeshoptError,
    _align4,
    _append_bytes,
    _read_glb,
    _write_glb,
)

WEIGHTS_ARRAY = "WEIGHTS_0"
JOINTS_ARRAY = "JOINTS_0"
HEAT_ATTR = "WEIGHT_EXHIBIT"

_COMPONENT_BYTES = {
    5120: 1,  # BYTE
    5121: 1,  # UNSIGNED_BYTE
    5122: 2,  # SHORT
    5123: 2,  # UNSIGNED_SHORT
    5125: 4,  # UNSIGNED_INT
    5126: 4,  # FLOAT
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


@dataclass(frozen=True)
class SkinJoint:
    """One entry in ``skin.joints``."""

    list_index: int
    node_index: int
    name: str


def gltf_has_skin_weights(gltf: dict[str, Any]) -> bool:
    """True when any mesh primitive declares JOINTS_0 + WEIGHTS_0."""
    for mesh in gltf.get("meshes") or []:
        if not isinstance(mesh, dict):
            continue
        for prim in mesh.get("primitives") or []:
            if not isinstance(prim, dict):
                continue
            attrs = prim.get("attributes") or {}
            if JOINTS_ARRAY in attrs and WEIGHTS_ARRAY in attrs:
                return True
    return False


def list_skin_joints(gltf: dict[str, Any], *, skin_index: int = 0) -> list[SkinJoint]:
    """Joint list for UI combo (first skin by default)."""
    skins = gltf.get("skins") or []
    if skin_index < 0 or skin_index >= len(skins):
        return []
    skin = skins[skin_index]
    if not isinstance(skin, dict):
        return []
    joints = skin.get("joints") or []
    nodes = gltf.get("nodes") or []
    result: list[SkinJoint] = []
    for list_index, node_index in enumerate(joints):
        try:
            node_i = int(node_index)
        except (TypeError, ValueError):
            continue
        name = f"Joint {list_index}"
        if 0 <= node_i < len(nodes) and isinstance(nodes[node_i], dict):
            raw = nodes[node_i].get("name")
            if isinstance(raw, str) and raw.strip():
                name = raw.strip()
        result.append(
            SkinJoint(list_index=list_index, node_index=node_i, name=name)
        )
    return result


def _accessor_stride(accessor: dict[str, Any], view: dict[str, Any]) -> int:
    ctype = int(accessor["componentType"])
    type_name = str(accessor.get("type") or "SCALAR")
    ncomp = _TYPE_COUNT.get(type_name, 1)
    tight = _COMPONENT_BYTES[ctype] * ncomp
    return int(view.get("byteStride") or tight)


def _read_vec_at(
    bin_chunk: bytes,
    accessor: dict[str, Any],
    view: dict[str, Any],
    index: int,
) -> tuple[float, ...]:
    ctype = int(accessor["componentType"])
    type_name = str(accessor.get("type") or "SCALAR")
    ncomp = _TYPE_COUNT.get(type_name, 1)
    stride = _accessor_stride(accessor, view)
    base = int(view.get("byteOffset") or 0) + int(accessor.get("byteOffset") or 0)
    offset = base + index * stride
    normalized = bool(accessor.get("normalized"))

    if ctype == 5126:
        fmt = "<" + ("f" * ncomp)
        return struct.unpack_from(fmt, bin_chunk, offset)
    if ctype == 5121:
        vals = struct.unpack_from("<" + ("B" * ncomp), bin_chunk, offset)
        if normalized:
            return tuple(v / 255.0 for v in vals)
        return tuple(float(v) for v in vals)
    if ctype == 5123:
        vals = struct.unpack_from("<" + ("H" * ncomp), bin_chunk, offset)
        if normalized:
            return tuple(v / 65535.0 for v in vals)
        return tuple(float(v) for v in vals)
    if ctype == 5125:
        vals = struct.unpack_from("<" + ("I" * ncomp), bin_chunk, offset)
        return tuple(float(v) for v in vals)
    raise MeshoptError(f"Unsupported accessor componentType {ctype}")


def _primitive_weight_heat(
    gltf: dict[str, Any],
    bin_chunk: bytes,
    prim: dict[str, Any],
    joint_list_index: int,
) -> bytes | None:
    attrs = prim.get("attributes") or {}
    if JOINTS_ARRAY not in attrs or WEIGHTS_ARRAY not in attrs:
        return None
    joints_i = int(attrs[JOINTS_ARRAY])
    weights_i = int(attrs[WEIGHTS_ARRAY])
    accessors = gltf.get("accessors") or []
    views = gltf.get("bufferViews") or []
    joints_acc = accessors[joints_i]
    weights_acc = accessors[weights_i]
    joints_view = views[int(joints_acc["bufferView"])]
    weights_view = views[int(weights_acc["bufferView"])]
    count = int(weights_acc["count"])
    if int(joints_acc["count"]) != count:
        raise MeshoptError("JOINTS_0 / WEIGHTS_0 count mismatch")

    out = bytearray()
    for vi in range(count):
        joints = _read_vec_at(bin_chunk, joints_acc, joints_view, vi)
        weights = _read_vec_at(bin_chunk, weights_acc, weights_view, vi)
        heat = 0.0
        for slot in range(min(4, len(joints), len(weights))):
            if int(joints[slot]) == joint_list_index:
                heat += float(weights[slot])
        if heat < 0.0:
            heat = 0.0
        elif heat > 1.0:
            heat = 1.0
        out.extend(struct.pack("<f", heat))
    return bytes(out)


def inject_joint_weight_heat(
    gltf: dict[str, Any],
    bin_chunk: bytes,
    joint_list_index: int,
    *,
    attr_name: str = HEAT_ATTR,
) -> bytes:
    """
    Append a SCALAR float attribute with influence of ``joint_list_index``.

    ``joint_list_index`` is the index into ``skin.joints`` (as stored in
    JOINTS_0), not the scene node index.
    """
    if joint_list_index < 0:
        raise MeshoptError("Invalid joint list index")

    new_bin = bytearray(bin_chunk)
    views = gltf.setdefault("bufferViews", [])
    accessors = gltf.setdefault("accessors", [])
    touched = False

    for mesh in gltf.get("meshes") or []:
        if not isinstance(mesh, dict):
            continue
        for prim in mesh.get("primitives") or []:
            if not isinstance(prim, dict):
                continue
            heat = _primitive_weight_heat(
                gltf, bin_chunk, prim, joint_list_index
            )
            if heat is None:
                continue
            offset = _append_bytes(new_bin, heat)
            view_index = len(views)
            views.append(
                {
                    "buffer": 0,
                    "byteOffset": offset,
                    "byteLength": len(heat),
                }
            )
            acc_index = len(accessors)
            accessors.append(
                {
                    "bufferView": view_index,
                    "componentType": 5126,
                    "count": len(heat) // 4,
                    "type": "SCALAR",
                    "max": [1.0],
                    "min": [0.0],
                }
            )
            attrs = prim.setdefault("attributes", {})
            attrs[attr_name] = acc_index
            touched = True

    if not touched:
        raise MeshoptError("No skinned primitives with JOINTS_0/WEIGHTS_0")

    pad = _align4(len(new_bin)) - len(new_bin)
    if pad:
        new_bin.extend(b"\x00" * pad)
    buffers = gltf.get("buffers")
    if buffers and isinstance(buffers[0], dict):
        buffers[0]["byteLength"] = len(new_bin)
    else:
        gltf["buffers"] = [{"byteLength": len(new_bin)}]
    return bytes(new_bin)


def write_skin_weight_heat_temp(
    src_path: str, joint_list_index: int
) -> str:
    """Write a temp GLB with ``WEIGHT_EXHIBIT`` for the selected joint."""
    gltf, bin_chunk = _read_glb(src_path)
    new_bin = inject_joint_weight_heat(gltf, bin_chunk, joint_list_index)
    fd, temp_path = tempfile.mkstemp(prefix="exhibit-skinw-", suffix=".glb")
    os.close(fd)
    try:
        _write_glb(temp_path, gltf, new_bin)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return temp_path


def mode_to_component(mode: str) -> int | None:
    """
    Map UI mode to WEIGHTS_0 scivis component.

    Returns ``None`` for bone-heat mode (uses HEAT_ATTR instead).
    """
    mapping = {
        "magnitude": -1,
        "slot0": 0,
        "slot1": 1,
        "slot2": 2,
        "slot3": 3,
    }
    if mode == "bone":
        return None
    if mode not in mapping:
        return -1
    return mapping[mode]


def cleanup_skin_weight_temp(path: str | None) -> None:
    if not path:
        return
    try:
        base = os.path.basename(path)
        if base.startswith("exhibit-skinw-"):
            os.unlink(path)
    except OSError:
        pass
