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
    _read_glb,
    _write_glb,
    cleanup_decompressed,
    prepare_glb_for_load,
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


def _load_prepared_gltf(path: str) -> dict[str, Any] | None:
    if not is_glb(path):
        return None

    load_path, temp_path = prepare_glb_for_load(path)
    try:
        try:
            gltf, _bin = _read_glb(load_path)
        except (OSError, MeshoptError):
            return None
        return gltf if isinstance(gltf, dict) else None
    finally:
        cleanup_decompressed(temp_path)


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


def build_scene_tree(path: str) -> list[SceneTreeNode]:
    """
    Return the glTF scene hierarchy as nested nodes.

    Runs meshopt/quantization preparation first so the graph matches what F3D
    loads. Returns an empty list for non-GLB paths or unreadable files.
    """
    gltf = _load_prepared_gltf(path)
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


def list_mesh_parts(path: str) -> list[ScenePart]:
    """
    Return mesh-bearing nodes from a GLB.

    Runs meshopt/quantization preparation first so the graph matches what F3D
    loads. Returns an empty list for non-GLB paths or unreadable files.
    """
    gltf = _load_prepared_gltf(path)
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


def write_glb_hiding_nodes(
    source_path: str, hidden_node_indices: set[int]
) -> tuple[str, str | None]:
    """
    Write a temporary GLB with ``mesh`` removed from hidden nodes.

    Returns ``(load_path, temp_path)``. ``temp_path`` must be cleaned up by the
    caller (may include the meshopt temp and/or the filtered temp).
    """
    if not is_glb(source_path):
        raise MeshoptError("Object visibility filtering supports .glb only")

    prepared_path, prepare_temp = prepare_glb_for_load(source_path)
    temps: list[str] = []
    if prepare_temp:
        temps.append(prepare_temp)

    try:
        gltf, bin_chunk = _read_glb(prepared_path)
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

        fd, filtered_path = tempfile.mkstemp(prefix="exhibit-parts-", suffix=".glb")
        os.close(fd)
        temps.append(filtered_path)
        _write_glb(filtered_path, gltf, bin_chunk)

        # Caller cleans a single temp; if we created both, delete prepare temp now
        # and return only the filtered path.
        if prepare_temp and prepare_temp != filtered_path:
            cleanup_decompressed(prepare_temp)
            temps = [filtered_path]

        return filtered_path, filtered_path
    except Exception:
        for path in temps:
            if path and os.path.basename(path).startswith("exhibit-"):
                try:
                    os.unlink(path)
                except OSError:
                    pass
        raise


def cleanup_parts_temp(path: str | None) -> None:
    """Delete a temporary GLB created by ``write_glb_hiding_nodes``."""
    if not path:
        return
    try:
        base = os.path.basename(path)
        if base.startswith("exhibit-parts-") or base.startswith("exhibit-meshopt-"):
            os.unlink(path)
    except OSError:
        pass
