# mesh_stats.py
#
# Copyright 2024-2026 Nokse <nokse@posteo.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh / scene statistics for overlays and AI manifests."""

from __future__ import annotations

import math
import os
import struct
from dataclasses import asdict, dataclass, field
from typing import Any

from .gltf_scene_graph import is_glb
from .meshopt_decompress import (
    MeshoptError,
    _COMPONENT_SIZE,
    _read_glb,
    _read_glb_json,
    prepare_glb_for_load,
    cleanup_decompressed,
    release_prepared,
)

_MODE_TRIANGLES = 4
_MODE_TRIANGLE_STRIP = 5
_MODE_TRIANGLE_FAN = 6
_MODE_LINES = 1
_MODE_LINE_LOOP = 2
_MODE_LINE_STRIP = 3
_MODE_POINTS = 0


class _LazyHeight:
    """Defer world-AABB height until overlay/manifest asks for it."""

    __slots__ = ("_gltf", "_up", "_value", "_done")

    def __init__(self, gltf: dict[str, Any], up: str = "+Y") -> None:
        self._gltf: dict[str, Any] | None = gltf
        self._up = up
        self._value: float | None = None
        self._done = False

    def get(self) -> float | None:
        if not self._done:
            gltf = self._gltf
            self._value = (
                _scene_height_m(gltf, up=self._up) if gltf is not None else None
            )
            self._done = True
            self._gltf = None
        return self._value


def _height_input_snapshot(gltf: dict[str, Any]) -> dict[str, Any]:
    """Slim copy: only fields needed for lazy height (drop BIN / big blobs)."""
    accessors_out: list[dict[str, Any]] = []
    for accessor in gltf.get("accessors") or []:
        if isinstance(accessor, dict) and "min" in accessor and "max" in accessor:
            accessors_out.append({"min": accessor["min"], "max": accessor["max"]})
        else:
            accessors_out.append({})

    nodes_out: list[dict[str, Any]] = []
    for node in gltf.get("nodes") or []:
        if not isinstance(node, dict):
            nodes_out.append({})
            continue
        slim: dict[str, Any] = {}
        for key in ("mesh", "children", "matrix", "translation", "rotation", "scale"):
            if key in node:
                slim[key] = node[key]
        nodes_out.append(slim)

    meshes_out: list[dict[str, Any]] = []
    for mesh in gltf.get("meshes") or []:
        if not isinstance(mesh, dict):
            meshes_out.append({})
            continue
        prims: list[dict[str, Any]] = []
        for prim in mesh.get("primitives") or []:
            if not isinstance(prim, dict):
                continue
            pos = (prim.get("attributes") or {}).get("POSITION")
            prims.append({"attributes": {"POSITION": pos}})
        meshes_out.append({"primitives": prims})

    return {
        "scene": gltf.get("scene", 0),
        "scenes": gltf.get("scenes"),
        "nodes": nodes_out,
        "meshes": meshes_out,
        "accessors": accessors_out,
    }


@dataclass(frozen=True)
class MeshStats:
    """Aggregated mesh / scene stats for a model file."""

    path: str
    file_bytes: int
    vertices: int | None = None
    faces: int | None = None
    edges: int | None = None
    edges_approximate: bool = False
    meshes: int | None = None
    primitives: int | None = None
    materials: int | None = None
    textures: int | None = None
    nodes: int | None = None
    skins: int | None = None
    animations: int | None = None
    morph_targets: int | None = None
    # Materialized world AABB height on the scene up axis (glTF units).
    height_m: float | None = None
    format: str | None = None
    # Private: cheap snapshot; height computed on first resolved_height_m().
    _lazy_height: _LazyHeight | None = field(
        default=None, repr=False, compare=False, hash=False
    )

    def resolved_height_m(self) -> float | None:
        """Return height, computing lazily from the GLTF snapshot if needed."""
        if self.height_m is not None:
            return self.height_m
        if self._lazy_height is None:
            return None
        return self._lazy_height.get()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("_lazy_height", None)
        data["height_m"] = self.resolved_height_m()
        return data


def _mat4_identity() -> list[float]:
    return [
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    ]


def _mat4_mul(a: list[float], b: list[float]) -> list[float]:
    """Column-major 4×4 multiply (glTF / Three.js)."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = (
                a[0 * 4 + row] * b[col * 4 + 0]
                + a[1 * 4 + row] * b[col * 4 + 1]
                + a[2 * 4 + row] * b[col * 4 + 2]
                + a[3 * 4 + row] * b[col * 4 + 3]
            )
    return out


def _mat4_from_trs(
    translation: list[float] | None,
    rotation: list[float] | None,
    scale: list[float] | None,
) -> list[float]:
    tx, ty, tz = (translation + [0.0, 0.0, 0.0])[:3] if translation else (0.0, 0.0, 0.0)
    sx, sy, sz = (scale + [1.0, 1.0, 1.0])[:3] if scale else (1.0, 1.0, 1.0)
    if rotation and len(rotation) >= 4:
        x, y, z, w = (float(rotation[i]) for i in range(4))
    else:
        x = y = z = 0.0
        w = 1.0

    x2, y2, z2 = x + x, y + y, z + z
    xx, xy, xz = x * x2, x * y2, x * z2
    yy, yz, zz = y * y2, y * z2, z * z2
    wx, wy, wz = w * x2, w * y2, w * z2

    return [
        (1.0 - (yy + zz)) * sx,
        (xy + wz) * sx,
        (xz - wy) * sx,
        0.0,
        (xy - wz) * sy,
        (1.0 - (xx + zz)) * sy,
        (yz + wx) * sy,
        0.0,
        (xz + wy) * sz,
        (yz - wx) * sz,
        (1.0 - (xx + yy)) * sz,
        0.0,
        tx,
        ty,
        tz,
        1.0,
    ]


def _node_local_matrix(node: dict[str, Any]) -> list[float]:
    matrix = node.get("matrix")
    if isinstance(matrix, list) and len(matrix) == 16:
        return [float(v) for v in matrix]
    translation = node.get("translation")
    rotation = node.get("rotation")
    scale = node.get("scale")
    t = [float(v) for v in translation] if isinstance(translation, list) else None
    r = [float(v) for v in rotation] if isinstance(rotation, list) else None
    s = [float(v) for v in scale] if isinstance(scale, list) else None
    return _mat4_from_trs(t, r, s)


def _world_matrices(gltf: dict[str, Any]) -> list[list[float]]:
    nodes = gltf.get("nodes") or []
    if not isinstance(nodes, list):
        return []

    children_of: dict[int, list[int]] = {i: [] for i in range(len(nodes))}
    has_parent = [False] * len(nodes)
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        for child in node.get("children") or []:
            if not isinstance(child, int) or child < 0 or child >= len(nodes):
                continue
            children_of[index].append(child)
            has_parent[child] = True

    worlds = [_mat4_identity() for _ in nodes]

    def visit(index: int, parent: list[float]) -> None:
        node = nodes[index]
        local = _node_local_matrix(node) if isinstance(node, dict) else _mat4_identity()
        world = _mat4_mul(parent, local)
        worlds[index] = world
        for child in children_of[index]:
            visit(child, world)

    roots = [i for i, flagged in enumerate(has_parent) if not flagged]
    scenes = gltf.get("scenes") or []
    scene_index = gltf.get("scene", 0)
    if isinstance(scenes, list) and isinstance(scene_index, int):
        if 0 <= scene_index < len(scenes) and isinstance(scenes[scene_index], dict):
            scene_roots = scenes[scene_index].get("nodes") or []
            if isinstance(scene_roots, list) and scene_roots:
                roots = [int(i) for i in scene_roots if isinstance(i, int)]

    for root in roots:
        if 0 <= root < len(nodes):
            visit(root, _mat4_identity())
    return worlds


def _accessor_local_aabb(
    accessor: dict[str, Any],
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    amin = accessor.get("min")
    amax = accessor.get("max")
    if (
        not isinstance(amin, list)
        or not isinstance(amax, list)
        or len(amin) < 3
        or len(amax) < 3
    ):
        return None
    return (
        (float(amin[0]), float(amin[1]), float(amin[2])),
        (float(amax[0]), float(amax[1]), float(amax[2])),
    )


def _transform_point(
    matrix: list[float], point: tuple[float, float, float]
) -> tuple[float, float, float]:
    x, y, z = point
    return (
        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    )


def _expand_aabb_with_oriented_box(
    scene_min: list[float],
    scene_max: list[float],
    local_min: tuple[float, float, float],
    local_max: tuple[float, float, float],
    world: list[float],
) -> None:
    """Expand scene AABB with the 8 corners of a local AABB (Three.js style)."""
    xs = (local_min[0], local_max[0])
    ys = (local_min[1], local_max[1])
    zs = (local_min[2], local_max[2])
    for x in xs:
        for y in ys:
            for z in zs:
                wx, wy, wz = _transform_point(world, (x, y, z))
                if wx < scene_min[0]:
                    scene_min[0] = wx
                if wy < scene_min[1]:
                    scene_min[1] = wy
                if wz < scene_min[2]:
                    scene_min[2] = wz
                if wx > scene_max[0]:
                    scene_max[0] = wx
                if wy > scene_max[1]:
                    scene_max[1] = wy
                if wz > scene_max[2]:
                    scene_max[2] = wz


_UP_AXIS = {
    "+X": 0,
    "-X": 0,
    "+Y": 1,
    "-Y": 1,
    "+Z": 2,
    "-Z": 2,
}


def _scene_height_m(gltf: dict[str, Any], up: str = "+Y") -> float | None:
    """
    World-space AABB extent along the scene up axis (glTF units).

    Uses POSITION accessor min/max transformed by node world matrices — same
    idea as ``Box3.setFromObject`` with geometry bounding boxes.
    """
    meshes = gltf.get("meshes") or []
    nodes = gltf.get("nodes") or []
    accessors = gltf.get("accessors") or []
    if not isinstance(meshes, list) or not isinstance(nodes, list):
        return None

    axis = _UP_AXIS.get(up, 1)
    worlds = _world_matrices(gltf)
    scene_min = [math.inf, math.inf, math.inf]
    scene_max = [-math.inf, -math.inf, -math.inf]
    found = False

    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        mesh_index = int(node["mesh"])
        if mesh_index < 0 or mesh_index >= len(meshes):
            continue
        mesh = meshes[mesh_index]
        if not isinstance(mesh, dict):
            continue
        world = worlds[node_index] if node_index < len(worlds) else _mat4_identity()
        for prim in mesh.get("primitives") or []:
            if not isinstance(prim, dict):
                continue
            attrs = prim.get("attributes") or {}
            pos = attrs.get("POSITION")
            if not isinstance(pos, int) or pos < 0 or pos >= len(accessors):
                continue
            accessor = accessors[pos]
            if not isinstance(accessor, dict):
                continue
            aabb = _accessor_local_aabb(accessor)
            if aabb is None:
                continue
            _expand_aabb_with_oriented_box(
                scene_min, scene_max, aabb[0], aabb[1], world
            )
            found = True

    if not found:
        return None
    height = scene_max[axis] - scene_min[axis]
    if not math.isfinite(height) or height < 0:
        return None
    return float(height)


def _accessor_count(gltf: dict[str, Any], accessor_index: int | None) -> int:
    if accessor_index is None:
        return 0
    accessors = gltf.get("accessors") or []
    if not isinstance(accessors, list):
        return 0
    if accessor_index < 0 or accessor_index >= len(accessors):
        return 0
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict):
        return 0
    return int(accessor.get("count") or 0)


def _read_indices(
    gltf: dict[str, Any], bin_chunk: bytes, accessor_index: int
) -> list[int] | None:
    accessors = gltf.get("accessors") or []
    views = gltf.get("bufferViews") or []
    if accessor_index < 0 or accessor_index >= len(accessors):
        return None
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict) or "bufferView" not in accessor:
        return None
    view_index = int(accessor["bufferView"])
    if view_index < 0 or view_index >= len(views):
        return None
    view = views[view_index]
    if not isinstance(view, dict):
        return None

    component_type = int(accessor.get("componentType") or 0)
    count = int(accessor.get("count") or 0)
    comp_size = _COMPONENT_SIZE.get(component_type)
    if not comp_size or count <= 0:
        return None

    # Sparse / meshopt-compressed views are skipped (stats still use counts).
    if (view.get("extensions") or {}).keys():
        return None

    fmt = {5121: "B", 5123: "H", 5125: "I"}.get(component_type)
    if fmt is None:
        return None

    byte_offset = int(view.get("byteOffset") or 0) + int(accessor.get("byteOffset") or 0)
    stride = int(view.get("byteStride") or comp_size)
    needed = byte_offset + stride * (count - 1) + comp_size
    if needed > len(bin_chunk):
        return None

    values: list[int] = []
    unpack = struct.Struct(f"<{fmt}").unpack_from
    for i in range(count):
        (value,) = unpack(bin_chunk, byte_offset + i * stride)
        values.append(int(value))
    return values


def _triangle_edges(indices: list[int]) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for i in range(0, len(indices) - 2, 3):
        a, b, c = indices[i], indices[i + 1], indices[i + 2]
        for u, v in ((a, b), (b, c), (c, a)):
            if u == v:
                continue
            edges.add((u, v) if u < v else (v, u))
    return edges


def _stats_from_gltf(
    path: str,
    gltf: dict[str, Any],
    bin_chunk: bytes | None,
    *,
    up: str = "+Y",
) -> MeshStats:
    meshes = gltf.get("meshes") or []
    materials = gltf.get("materials") or []
    textures = gltf.get("textures") or []
    nodes = gltf.get("nodes") or []
    skins = gltf.get("skins") or []
    animations = gltf.get("animations") or []

    vertices = 0
    faces = 0
    primitives = 0
    morph_targets = 0
    edge_set: set[tuple[int, int]] = set()
    edges_exact = True
    # Offset local indices so edges from distinct primitives do not collide.
    vertex_base = 0

    for mesh in meshes if isinstance(meshes, list) else []:
        if not isinstance(mesh, dict):
            continue
        for prim in mesh.get("primitives") or []:
            if not isinstance(prim, dict):
                continue
            primitives += 1
            attrs = prim.get("attributes") or {}
            pos = attrs.get("POSITION")
            vert_count = _accessor_count(gltf, int(pos) if pos is not None else None)
            vertices += vert_count
            base = vertex_base
            vertex_base += max(vert_count, 0)

            targets = prim.get("targets") or []
            if isinstance(targets, list):
                morph_targets += len(targets)

            mode = int(prim.get("mode", _MODE_TRIANGLES))
            indices_idx = prim.get("indices")

            if mode in (_MODE_TRIANGLES, _MODE_TRIANGLE_STRIP, _MODE_TRIANGLE_FAN):
                if indices_idx is not None:
                    idx_count = _accessor_count(gltf, int(indices_idx))
                    if mode == _MODE_TRIANGLES:
                        faces += idx_count // 3
                    elif mode == _MODE_TRIANGLE_STRIP:
                        faces += max(idx_count - 2, 0)
                    else:  # fan
                        faces += max(idx_count - 2, 0)
                    if (
                        edges_exact
                        and bin_chunk is not None
                        and mode == _MODE_TRIANGLES
                    ):
                        indices = _read_indices(gltf, bin_chunk, int(indices_idx))
                        if indices is None:
                            edges_exact = False
                        else:
                            offset = [
                                base + int(i) for i in indices
                            ]
                            edge_set |= _triangle_edges(offset)
                    else:
                        edges_exact = False
                else:
                    # Non-indexed triangles
                    if mode == _MODE_TRIANGLES:
                        faces += vert_count // 3
                    else:
                        faces += max(vert_count - 2, 0)
                    edges_exact = False
            elif mode in (_MODE_LINES, _MODE_LINE_LOOP, _MODE_LINE_STRIP):
                edges_exact = False
            elif mode == _MODE_POINTS:
                pass

    edges: int | None
    edges_approximate = False
    if edges_exact and edge_set:
        edges = len(edge_set)
    elif faces > 0:
        # Closed-manifold estimate; marked as approximate in overlay text.
        edges = int(round(faces * 1.5))
        edges_approximate = True
    else:
        edges = None

    try:
        file_bytes = int(os.path.getsize(path))
    except OSError:
        file_bytes = 0

    return MeshStats(
        path=os.path.abspath(path),
        file_bytes=file_bytes,
        vertices=vertices or None,
        faces=faces or None,
        edges=edges,
        edges_approximate=edges_approximate,
        meshes=len(meshes) if isinstance(meshes, list) else 0,
        primitives=primitives,
        materials=len(materials) if isinstance(materials, list) else 0,
        textures=len(textures) if isinstance(textures, list) else 0,
        nodes=len(nodes) if isinstance(nodes, list) else 0,
        skins=len(skins) if isinstance(skins, list) else 0,
        animations=len(animations) if isinstance(animations, list) else 0,
        morph_targets=morph_targets or None,
        format="glb",
        # Height is O(nodes×prims) via min/max corners — still deferred until
        # overlay / manifest asks (never scans vertex buffers).
        _lazy_height=_LazyHeight(_height_input_snapshot(gltf), up=up),
    )


def collect_mesh_stats(
    path: str, *, already_prepared: bool = False, up: str = "+Y"
) -> MeshStats:
    """
    Collect stats for ``path``.

    For ``.glb``, prepares meshopt/quantization when needed so counts match
    what F3D loads. Non-GLB returns file size only.
    """
    abs_path = os.path.abspath(path)
    try:
        file_bytes = int(os.path.getsize(abs_path))
    except OSError:
        file_bytes = 0

    if not is_glb(abs_path):
        ext = os.path.splitext(abs_path)[1].lstrip(".").lower() or None
        return MeshStats(path=abs_path, file_bytes=file_bytes, format=ext)

    temp = None
    load_path = abs_path
    retained = False
    if not already_prepared:
        try:
            load_path, temp = prepare_glb_for_load(abs_path)
            retained = load_path != abs_path and temp is None
        except (OSError, MeshoptError):
            return MeshStats(path=abs_path, file_bytes=file_bytes, format="glb")

    try:
        try:
            gltf, bin_chunk = _read_glb(load_path)
        except (OSError, MeshoptError):
            # JSON-only fallback (no edge exactness).
            try:
                gltf = _read_glb_json(load_path)
            except (OSError, MeshoptError):
                return MeshStats(path=abs_path, file_bytes=file_bytes, format="glb")
            return _stats_from_gltf(abs_path, gltf, None, up=up)
        return _stats_from_gltf(abs_path, gltf, bin_chunk, up=up)
    finally:
        cleanup_decompressed(temp)
        if retained:
            release_prepared(load_path)


def format_overlay_text(stats: MeshStats, *, approximate_edges: bool = False) -> str:
    """Human-readable multi-line overlay / filename_info text."""
    lines: list[str] = []
    name = os.path.basename(stats.path)
    lines.append(name)

    def _fmt(n: int | None) -> str:
        if n is None:
            return "—"
        return f"{n:,}"

    def _row(label: str, value: str) -> str:
        return f"{label:<7}{value}"

    if stats.file_bytes:
        if stats.file_bytes >= 1024 * 1024:
            size_s = f"{stats.file_bytes / (1024 * 1024):.2f} MiB"
        elif stats.file_bytes >= 1024:
            size_s = f"{stats.file_bytes / 1024:.1f} KiB"
        else:
            size_s = f"{stats.file_bytes} B"
        lines.append(_row("Size", size_s))

    height = stats.resolved_height_m()
    if height is not None:
        if height >= 100:
            height_s = f"{height:.1f} m"
        elif height >= 1:
            height_s = f"{height:.2f} m"
        elif height >= 0.01:
            height_s = f"{height:.3f} m"
        else:
            height_s = f"{height:.4f} m"
        lines.append(_row("Height", height_s))

    if stats.vertices is not None:
        lines.append(_row("Verts", _fmt(stats.vertices)))
    if stats.faces is not None:
        lines.append(_row("Faces", _fmt(stats.faces)))
    if stats.edges is not None:
        mark = "~" if stats.edges_approximate or approximate_edges else ""
        lines.append(_row("Edges", f"{mark}{_fmt(stats.edges)}"))

    meta: list[str] = []
    if stats.meshes is not None:
        meta.append(f"Meshes {_fmt(stats.meshes)}")
    if stats.primitives is not None:
        meta.append(f"Prims {_fmt(stats.primitives)}")
    if stats.materials is not None:
        meta.append(f"Mats {_fmt(stats.materials)}")
    if stats.textures is not None:
        meta.append(f"Tex {_fmt(stats.textures)}")
    if stats.nodes is not None:
        meta.append(f"Nodes {_fmt(stats.nodes)}")
    if stats.skins is not None and stats.skins > 0:
        meta.append(f"Skins {_fmt(stats.skins)}")
    if stats.animations is not None and stats.animations > 0:
        meta.append(f"Anims {_fmt(stats.animations)}")
    if stats.morph_targets is not None and stats.morph_targets > 0:
        meta.append(f"Morph {_fmt(stats.morph_targets)}")
    if meta:
        lines.append(" · ".join(meta))

    return "\n".join(lines)


def format_overlay_for_f3d(stats: MeshStats) -> str:
    """Single-block text suitable for ``ui.filename_info`` (F3D overlay)."""
    return format_overlay_text(stats)
