# SPDX-License-Identifier: GPL-3.0-or-later
"""Expanded gltf_scene_graph coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from exhibit.gltf_scene_graph import (
    ScenePart,
    SceneTreeNode,
    _build_tree_node,
    _depth_and_path,
    _effective_hidden,
    _node_name,
    _parent_map,
    _scene_root_indices,
    build_glb_hiding_nodes_bytes,
    build_scene_tree,
    cleanup_parts_temp,
    glb_has_skins,
    is_glb,
    is_gltf_or_glb,
    list_mesh_parts,
    tree_has_mesh,
    write_glb_hiding_nodes,
)
from exhibit.meshopt_decompress import MeshoptError, _read_glb, clear_prepare_cache
from tests.glb_factory import (
    empty_scene_gltf,
    multipart_gltf,
    plain_triangle_gltf,
    write_glb,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_prepare_cache()
    yield
    clear_prepare_cache()


@pytest.mark.parametrize(
    "path,expected",
    [
        ("a.glb", True),
        ("A.GLB", True),
        ("/tmp/x.Glb", True),
        ("a.gltf", False),
        ("a.glb.bak", False),
        ("", False),
        (None, False),
        ("model.obj", False),
    ],
)
def test_is_glb_matrix(path, expected):
    assert is_glb(path) is expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("a.glb", True),
        ("a.gltf", True),
        ("A.GLTF", True),
        ("a.Glb", True),
        ("", False),
        (None, False),
        ("a.fbx", False),
        ("model.gltf.json", False),
        ("x.glb.txt", False),
    ],
)
def test_is_gltf_or_glb_matrix(path, expected):
    assert is_gltf_or_glb(path) is expected


@pytest.mark.parametrize(
    "nodes,index,expected",
    [
        ([{"mesh": 0}], 0, "Mesh 0"),
        ([{"mesh": 3}], 0, "Mesh 3"),
        ([{"name": "  "}], 0, "Node 0"),
        ([{"name": ""}], 0, "Node 0"),
        ([{"name": "Hero"}], 0, "Hero"),
        ([{"name": "A"}, {"name": "B", "mesh": 1}], 1, "B"),
        ([{}], 0, "Node 0"),
    ],
)
def test_node_name_matrix(nodes, index, expected):
    assert _node_name(nodes, index) == expected


def test_parent_map_basic():
    nodes = [{"children": [1, 2]}, {}, {"children": [3]}, {}]
    assert _parent_map(nodes) == {1: 0, 2: 0, 3: 2}


def test_depth_and_path_labels():
    nodes = [
        {"name": "Root", "children": [1]},
        {"name": "Child", "mesh": 0},
    ]
    parents = _parent_map(nodes)
    depth, label = _depth_and_path(nodes, 1, parents)
    assert depth == 1
    assert label == "Root / Child"


@pytest.mark.parametrize(
    "hidden,expected",
    [
        (set(), set()),
        ({1}, {1}),
        ({0}, {0, 1, 2, 3}),
        ({2}, {2, 3}),
        ({3}, {3}),
        ({1, 3}, {1, 3}),
    ],
)
def test_effective_hidden_matrix(hidden, expected):
    nodes = [
        {"children": [1, 2]},
        {"mesh": 0},
        {"children": [3]},
        {"mesh": 0},
    ]
    assert _effective_hidden(nodes, hidden) == expected


def test_scene_root_indices_from_scene():
    gltf = {"scene": 0, "scenes": [{"nodes": [2]}], "nodes": [{}, {}, {}]}
    assert _scene_root_indices(gltf, gltf["nodes"]) == [2]


def test_scene_root_indices_fallback_orphans():
    nodes = [{"children": [1]}, {}, {}]
    gltf = {}
    roots = _scene_root_indices(gltf, nodes)
    assert 0 in roots
    assert 2 in roots
    assert 1 not in roots


def test_build_tree_node_cycle_guard():
    nodes = [{"children": [0], "name": "Loop"}]
    built = _build_tree_node(nodes, 0, set())
    assert built is not None
    assert built.name == "Loop"
    assert built.children == ()


def test_tree_has_mesh_true_false():
    leaf = SceneTreeNode(0, "A", True, ())
    empty = SceneTreeNode(1, "B", False, ())
    parent = SceneTreeNode(2, "P", False, (empty, leaf))
    assert tree_has_mesh([parent]) is True
    assert tree_has_mesh([empty]) is False
    assert tree_has_mesh([]) is False


def test_build_scene_tree_empty_file(tmp_path: Path):
    gltf, bin_chunk = empty_scene_gltf()
    path = write_glb(tmp_path / "e.glb", gltf, bin_chunk)
    tree = build_scene_tree(str(path))
    assert len(tree) == 1
    assert tree[0].name == "Empty"
    assert tree[0].has_mesh is False
    assert list_mesh_parts(str(path)) == []


def test_build_scene_tree_non_gltf(tmp_path: Path):
    path = tmp_path / "a.obj"
    path.write_text("v 0 0 0\n")
    assert build_scene_tree(str(path)) == []
    assert list_mesh_parts(str(path)) == []


def test_list_mesh_parts_plain(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "t.glb", gltf, bin_chunk)
    parts = list_mesh_parts(str(path))
    assert len(parts) == 1
    assert isinstance(parts[0], ScenePart)
    assert parts[0].name == "Tri"
    assert parts[0].depth == 0


def test_hide_root_hides_all_parts(tmp_path: Path):
    gltf, bin_chunk = multipart_gltf()
    path = write_glb(tmp_path / "m.glb", gltf, bin_chunk)
    data = build_glb_hiding_nodes_bytes(str(path), {0})
    out = tmp_path / "h.glb"
    out.write_bytes(data)
    out_gltf, _ = _read_glb(str(out))
    for node in out_gltf["nodes"]:
        assert "mesh" not in node


def test_hide_empty_set_keeps_meshes(tmp_path: Path):
    gltf, bin_chunk = multipart_gltf()
    path = write_glb(tmp_path / "m.glb", gltf, bin_chunk)
    data = build_glb_hiding_nodes_bytes(str(path), set())
    out = tmp_path / "h.glb"
    out.write_bytes(data)
    out_gltf, _ = _read_glb(str(out))
    assert "mesh" in out_gltf["nodes"][1]
    assert "mesh" in out_gltf["nodes"][2]


def test_write_glb_hiding_nodes_and_cleanup(tmp_path: Path):
    gltf, bin_chunk = multipart_gltf()
    path = write_glb(tmp_path / "m.glb", gltf, bin_chunk)
    load_path, temp = write_glb_hiding_nodes(str(path), {1})
    assert temp is not None
    assert Path(load_path).exists()
    out_gltf, _ = _read_glb(load_path)
    assert "mesh" not in out_gltf["nodes"][1]
    cleanup_parts_temp(temp)
    assert not Path(temp).exists()


def test_cleanup_parts_temp_ignores_other_names(tmp_path: Path):
    path = tmp_path / "other.glb"
    path.write_bytes(b"x")
    cleanup_parts_temp(str(path))
    assert path.exists()
    cleanup_parts_temp(None)


def test_hide_non_gltf_raises(tmp_path: Path):
    path = tmp_path / "a.obj"
    path.write_text("v 0 0 0\n")
    with pytest.raises(MeshoptError, match="visibility filtering"):
        build_glb_hiding_nodes_bytes(str(path), {0})


def test_glb_has_skins_non_gltf(tmp_path: Path):
    path = tmp_path / "a.obj"
    path.write_text("v 0 0 0\n")
    assert glb_has_skins(str(path)) is None


def test_glb_has_skins_empty_list(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    gltf["skins"] = []
    path = write_glb(tmp_path / "s.glb", gltf, bin_chunk)
    assert glb_has_skins(str(path)) is False


def test_scene_tree_multipart_structure(tmp_path: Path):
    gltf, bin_chunk = multipart_gltf()
    path = write_glb(tmp_path / "m.glb", gltf, bin_chunk)
    tree = build_scene_tree(str(path))
    assert tree_has_mesh(tree) is True
    assert {c.name for c in tree[0].children} == {"PartA", "PartB"}
