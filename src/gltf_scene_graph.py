# gltf_scene_graph.py
#
# Copyright 2024-2025 Nokse <nokse@posteo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""glTF/GLB scene-graph helpers for multipart object visibility."""

from __future__ import annotations

import copy
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from .meshopt_decompress import (
    MeshoptError,
    _glb_bytes,
    _read_glb,
    _read_glb_json,
    cleanup_decompressed,
    prepare_glb_for_load,
    release_prepared,
)


@dataclass(frozen=True)
class ScenePart:
    """A glTF node that references a mesh (a visible 'part')."""

    index: int
    name: str
    depth: int
    path_label: str


@dataclass(frozen=True)
class SceneTreeNode:
    """A glTF node in the scene hierarchy (mesh or structural)."""

    index: int
    name: str
    has_mesh: bool
    children: tuple["SceneTreeNode", ...] = ()


def is_glb(path: str) -> bool:
    return bool(path) and str(path).lower().endswith(".glb")


def is_gltf_or_glb(path: str) -> bool:
    if not path:
        return False
    lower = str(path).lower()
    return lower.endswith(".glb") or lower.endswith(".gltf")


def glb_has_skins(path: str) -> bool | None:
    """
    Return whether a GLB/glTF declares skins (armature).

    ``None`` means the file is not a readable glTF asset (unknown / N/A).
    """
    if not is_gltf_or_glb(path):
        return None
    try:
        if is_glb(path):
            gltf = _read_glb_json(path)
        else:
            prepared, temp = prepare_glb_for_load(path)
            try:
                gltf = _read_glb_json(prepared)
            finally:
                cleanup_decompressed(temp)
                if prepared != path and temp is None:
                    release_prepared(prepared)
    except (OSError, MeshoptError):
        return None
    skins = gltf.get("skins") or []
    return isinstance(skins, list) and len(skins) > 0


def _joint_parent_map(nodes: list[Any]) -> dict[int, int]:
    parents: dict[int, int] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        for child in node.get("children") or []:
            try:
                parents[int(child)] = index
            except (TypeError, ValueError):
                continue
    return parents


def _infer_skin_skeleton(gltf: dict[str, Any], joints: list[int]) -> int | None:
    """Pick a skeleton root joint for skins that omit ``skeleton``."""
    if not joints:
        return None
    nodes = gltf.get("nodes") or []
    joint_set = {int(j) for j in joints}
    parents = _joint_parent_map(nodes if isinstance(nodes, list) else [])
    roots = [j for j in joint_set if parents.get(j) not in joint_set]
    if len(roots) == 1:
        return roots[0]
    # Prefer first joint listed that is a root (gltfpack order).
    for joint in joints:
        if int(joint) in roots:
            return int(joint)
    return int(joints[0])


def gltf_needs_skin_skeleton_fix(gltf: dict[str, Any]) -> bool:
    """True when a skin has joints but no valid ``skeleton`` root index."""
    nodes = gltf.get("nodes") or []
    n_nodes = len(nodes) if isinstance(nodes, list) else 0
    for skin in gltf.get("skins") or []:
        if not isinstance(skin, dict):
            continue
        joints = skin.get("joints")
        if not isinstance(joints, list) or not joints:
            continue
        skeleton = skin.get("skeleton")
        if not isinstance(skeleton, int) or skeleton < 0 or skeleton >= n_nodes:
            return True
    return False


def ensure_skin_skeletons(gltf: dict[str, Any]) -> bool:
    """
    Fill missing ``skin.skeleton`` so F3D/VTK can build armature actors.

    VTK only creates armature polydata when ``skeleton >= 0``. Many gltfpack
    assets omit the optional field even though ``joints`` is populated.
    """
    nodes = gltf.get("nodes") or []
    if not isinstance(nodes, list):
        return False
    n_nodes = len(nodes)
    changed = False
    for skin in gltf.get("skins") or []:
        if not isinstance(skin, dict):
            continue
        joints_raw = skin.get("joints")
        if not isinstance(joints_raw, list) or not joints_raw:
            continue
        try:
            joints = [int(j) for j in joints_raw]
        except (TypeError, ValueError):
            continue
        skeleton = skin.get("skeleton")
        if isinstance(skeleton, int) and 0 <= skeleton < n_nodes:
            continue
        root = _infer_skin_skeleton(gltf, joints)
        if root is None or not (0 <= root < n_nodes):
            continue
        skin["skeleton"] = root
        changed = True
    return changed


def _node_name(nodes: list[dict[str, Any]], index: int) -> str:
    node = nodes[index]
    name = node.get("name")
    if isinstance(name, str) and name.strip():
        return name
    if "mesh" in node:
        return f"Mesh {node['mesh']}"
    return f"Node {index}"


def _parent_map(nodes: list[dict[str, Any]]) -> dict[int, int]:
    parents: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children") or []:
            parents[int(child)] = index
    return parents


def _depth_and_path(
    nodes: list[dict[str, Any]], index: int, parents: dict[int, int]
) -> tuple[int, str]:
    chain: list[str] = []
    current: int | None = index
    guard = 0
    while current is not None and guard < len(nodes) + 1:
        chain.append(_node_name(nodes, current))
        current = parents.get(current)
        guard += 1
    chain.reverse()
    return len(chain) - 1, " / ".join(chain)


def _load_gltf(path: str, *, already_prepared: bool = False) -> dict[str, Any] | None:
    if not is_gltf_or_glb(path):
        return None

    temp_path = None
    load_path = path
    retained = False
    if not already_prepared:
        load_path, temp_path = prepare_glb_for_load(path)
        retained = load_path != path and temp_path is None
    try:
        try:
            gltf, _bin = _read_glb(load_path)
        except (OSError, MeshoptError):
            return None
        return gltf if isinstance(gltf, dict) else None
    finally:
        cleanup_decompressed(temp_path)
        if retained:
            release_prepared(load_path)


def _scene_root_indices(gltf: dict[str, Any], nodes: list[dict[str, Any]]) -> list[int]:
    scenes = gltf.get("scenes") or []
    scene_idx = gltf.get("scene", 0)
    if isinstance(scenes, list) and isinstance(scene_idx, int):
        if 0 <= scene_idx < len(scenes) and isinstance(scenes[scene_idx], dict):
            roots = scenes[scene_idx].get("nodes") or []
            if isinstance(roots, list) and roots:
                return [int(i) for i in roots if isinstance(i, int) or str(i).isdigit()]

    parents = _parent_map(nodes)
    return [index for index in range(len(nodes)) if index not in parents]


def _build_tree_node(
    nodes: list[dict[str, Any]], index: int, seen: set[int]
) -> SceneTreeNode | None:
    if index < 0 or index >= len(nodes) or index in seen:
        return None
    node = nodes[index]
    if not isinstance(node, dict):
        return None

    seen.add(index)
    children: list[SceneTreeNode] = []
    for child in node.get("children") or []:
        child_index = int(child)
        built = _build_tree_node(nodes, child_index, seen)
        if built is not None:
            children.append(built)

    return SceneTreeNode(
        index=index,
        name=_node_name(nodes, index),
        has_mesh="mesh" in node,
        children=tuple(children),
    )


def tree_has_mesh(roots: list[SceneTreeNode]) -> bool:
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node.has_mesh:
            return True
        stack.extend(node.children)
    return False


def build_scene_tree(
    path: str, *, already_prepared: bool = False
) -> list[SceneTreeNode]:
    """
    Return the glTF scene hierarchy as nested nodes.

    Runs meshopt/quantization preparation first so the graph matches what F3D
    loads (unless ``already_prepared``). Returns an empty list for non-GLB
    paths or unreadable files.
    """
    gltf = _load_gltf(path, already_prepared=already_prepared)
    if not gltf:
        return []

    nodes = gltf.get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        return []

    roots: list[SceneTreeNode] = []
    seen: set[int] = set()
    for root_index in _scene_root_indices(gltf, nodes):
        built = _build_tree_node(nodes, int(root_index), seen)
        if built is not None:
            roots.append(built)
    return roots


def list_mesh_parts(path: str, *, already_prepared: bool = False) -> list[ScenePart]:
    """
    Return mesh-bearing nodes from a GLB.

    Runs meshopt/quantization preparation first so the graph matches what F3D
    loads (unless ``already_prepared``). Returns an empty list for non-GLB
    paths or unreadable files.
    """
    gltf = _load_gltf(path, already_prepared=already_prepared)
    if not gltf:
        return []

    nodes = gltf.get("nodes") or []
    if not isinstance(nodes, list):
        return []

    parents = _parent_map(nodes)
    parts: list[ScenePart] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        depth, path_label = _depth_and_path(nodes, index, parents)
        parts.append(
            ScenePart(
                index=index,
                name=_node_name(nodes, index),
                depth=depth,
                path_label=path_label,
            )
        )
    return parts


def _effective_hidden(nodes: list[dict[str, Any]], hidden: set[int]) -> set[int]:
    """Expand hidden set so descendants of a hidden node are also hidden."""
    parents = _parent_map(nodes)
    result = set(hidden)
    changed = True
    while changed:
        changed = False
        for index in range(len(nodes)):
            if index in result:
                continue
            parent = parents.get(index)
            if parent is not None and parent in result:
                result.add(index)
                changed = True
    return result


def _filter_glb_hiding_nodes(
    source_path: str,
    hidden_node_indices: set[int],
    *,
    prepared_path: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    """
    Build filtered glTF + BIN with ``mesh`` removed from hidden nodes.

    When ``prepared_path`` is given, that file is used as-is (no meshopt
    prepare). Caller must not mutate the returned structures after use.
    """
    if not is_gltf_or_glb(source_path) and not (
        prepared_path and is_glb(prepared_path)
    ):
        raise MeshoptError(
            "Object visibility filtering supports .glb / .gltf only"
        )

    prepare_temp = None
    retained_prepare = None
    if prepared_path:
        prepared = prepared_path
    else:
        prepared, prepare_temp = prepare_glb_for_load(source_path)
        if prepare_temp is None and prepared != source_path:
            retained_prepare = prepared

    try:
        gltf, bin_chunk = _read_glb(prepared)
        nodes = gltf.get("nodes") or []
        if not isinstance(nodes, list):
            raise MeshoptError("Invalid glTF nodes")

        # Work on a deep copy so preparation caches stay untouched.
        gltf = copy.deepcopy(gltf)
        nodes = gltf["nodes"]
        effective = _effective_hidden(nodes, set(hidden_node_indices))

        for index, node in enumerate(nodes):
            if index in effective and isinstance(node, dict):
                node.pop("mesh", None)

        return gltf, bin_chunk
    finally:
        if prepare_temp:
            cleanup_decompressed(prepare_temp)
        if retained_prepare:
            release_prepared(retained_prepare)


def build_glb_hiding_nodes_bytes(
    source_path: str,
    hidden_node_indices: set[int],
    *,
    prepared_path: str | None = None,
) -> bytes:
    """Return an in-memory GLB with hidden node meshes stripped."""
    gltf, bin_chunk = _filter_glb_hiding_nodes(
        source_path,
        hidden_node_indices,
        prepared_path=prepared_path,
    )
    return _glb_bytes(gltf, bin_chunk)


def write_glb_hiding_nodes(
    source_path: str,
    hidden_node_indices: set[int],
    *,
    prepared_path: str | None = None,
) -> tuple[str, str | None]:
    """
    Write a temporary GLB with ``mesh`` removed from hidden nodes.

    When ``prepared_path`` is given, that file is used as-is (no meshopt
    prepare). Returns ``(load_path, temp_path)``. ``temp_path`` must be cleaned
    up by the caller.
    """
    data = build_glb_hiding_nodes_bytes(
        source_path,
        hidden_node_indices,
        prepared_path=prepared_path,
    )
    fd, filtered_path = tempfile.mkstemp(prefix="exhibit-parts-", suffix=".glb")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except Exception:
        try:
            os.unlink(filtered_path)
        except OSError:
            pass
        raise
    return filtered_path, filtered_path


def cleanup_parts_temp(path: str | None) -> None:
    """Delete a temporary GLB created by ``write_glb_hiding_nodes``."""
    if not path:
        return
    try:
        # Only parts temps — never touch prepare-cache meshopt files.
        if os.path.basename(path).startswith("exhibit-parts-"):
            os.unlink(path)
    except OSError:
        pass
