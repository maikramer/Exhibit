# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from exhibit.gltf_scene_graph import (
    _effective_hidden,
    _infer_skin_skeleton,
    _node_name,
    build_glb_hiding_nodes_bytes,
    build_scene_tree,
    ensure_skin_skeletons,
    glb_has_skins,
    gltf_needs_skin_skeleton_fix,
    is_glb,
    list_mesh_parts,
)
from exhibit.meshopt_decompress import (
    _read_glb,
    clear_prepare_cache,
    needs_glb_prepare,
    prepare_glb_for_load,
    release_prepared,
)
from tests.glb_factory import multipart_gltf, plain_triangle_gltf, write_glb


def setup_function():
    clear_prepare_cache()


def teardown_function():
    clear_prepare_cache()


def test_is_glb():
    assert is_glb("a.glb")
    assert is_glb("A.GLB")
    assert not is_glb("a.gltf")
    assert not is_glb("")


def test_node_name_defaults():
    nodes = [{"mesh": 0}, {"name": "  "}, {"name": "Hero"}]
    assert _node_name(nodes, 0) == "Mesh 0"
    assert _node_name(nodes, 1) == "Node 1"
    assert _node_name(nodes, 2) == "Hero"


def test_effective_hidden_propagates_children():
    nodes = [
        {"children": [1, 2]},
        {"mesh": 0},
        {"children": [3]},
        {"mesh": 0},
    ]
    assert _effective_hidden(nodes, {0}) == {0, 1, 2, 3}
    assert _effective_hidden(nodes, {2}) == {2, 3}
    assert _effective_hidden(nodes, {1}) == {1}


def test_scene_tree_and_parts(tmp_path: Path):
    gltf, bin_chunk = multipart_gltf()
    path = write_glb(tmp_path / "multi.glb", gltf, bin_chunk)
    tree = build_scene_tree(str(path))
    assert len(tree) == 1
    assert tree[0].name == "Root"
    assert len(tree[0].children) == 2
    parts = list_mesh_parts(str(path))
    names = {p.name for p in parts}
    assert names == {"PartA", "PartB"}


def test_hide_nodes_strips_mesh(tmp_path: Path):
    gltf, bin_chunk = multipart_gltf()
    path = write_glb(tmp_path / "multi.glb", gltf, bin_chunk)
    # Hide PartA (node index 1)
    data = build_glb_hiding_nodes_bytes(str(path), {1})
    out = tmp_path / "hidden.glb"
    out.write_bytes(data)
    out_gltf, _ = _read_glb(str(out))
    assert "mesh" not in out_gltf["nodes"][1]
    assert "mesh" in out_gltf["nodes"][2]


def test_glb_has_skins_false(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    path = write_glb(tmp_path / "plain.glb", gltf, bin_chunk)
    assert glb_has_skins(str(path)) is False


def test_glb_has_skins_true(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    gltf["skins"] = [{"joints": [0]}]
    gltf["nodes"][0]["skin"] = 0
    path = write_glb(tmp_path / "skinned.glb", gltf, bin_chunk)
    assert glb_has_skins(str(path)) is True


def test_ensure_skin_skeletons_infers_root():
    gltf = {
        "nodes": [
            {"name": "root", "children": [1]},
            {"name": "bone", "children": [2]},
            {"name": "tip"},
            {"name": "Mesh", "mesh": 0, "skin": 0},
        ],
        "skins": [{"name": "Armature", "joints": [0, 1, 2]}],
    }
    assert gltf_needs_skin_skeleton_fix(gltf) is True
    assert _infer_skin_skeleton(gltf, [0, 1, 2]) == 0
    assert ensure_skin_skeletons(gltf) is True
    assert gltf["skins"][0]["skeleton"] == 0
    assert gltf_needs_skin_skeleton_fix(gltf) is False
    assert ensure_skin_skeletons(gltf) is False


def test_ensure_skin_skeletons_keeps_existing():
    gltf = {
        "nodes": [{"name": "a"}, {"name": "b"}],
        "skins": [{"joints": [0, 1], "skeleton": 1}],
    }
    assert gltf_needs_skin_skeleton_fix(gltf) is False
    assert ensure_skin_skeletons(gltf) is False
    assert gltf["skins"][0]["skeleton"] == 1


def test_prepare_fills_missing_skin_skeleton(tmp_path: Path):
    gltf, bin_chunk = plain_triangle_gltf()
    # Two-node chain: 0 parent of 1; skin joints without skeleton.
    gltf["nodes"] = [
        {"name": "root", "children": [1]},
        {"name": "bone"},
        {"name": "Mesh", "mesh": 0, "skin": 0},
    ]
    gltf["scenes"] = [{"nodes": [0, 2]}]
    gltf["skins"] = [{"joints": [0, 1], "inverseBindMatrices": 0}]
    # Minimal IBM accessor pointing at existing bufferView 0 (OK for prepare JSON rewrite).
    path = write_glb(tmp_path / "noskel.glb", gltf, bin_chunk)
    assert needs_glb_prepare(str(path)) is True
    load_path, _ = prepare_glb_for_load(str(path))
    try:
        out, _ = _read_glb(load_path)
        assert out["skins"][0].get("skeleton") == 0
    finally:
        release_prepared(load_path)
