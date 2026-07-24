# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from exhibit.drop_paths import DEFAULT_MAX_BATCH_OPEN, collect_openable_model_paths


def test_collect_openable_model_paths_files_and_folder(tmp_path: Path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "a.glb").write_bytes(b"x")
    (models / "b.gltf").write_bytes(b"y")
    (models / "readme.txt").write_text("nope")
    nested = models / "nested"
    nested.mkdir()
    (nested / "c.glb").write_bytes(b"z")
    lone = tmp_path / "solo.glb"
    lone.write_bytes(b"s")

    paths = collect_openable_model_paths(
        [str(lone), str(models)],
        allowed_exts=["glb", "gltf"],
    )
    assert str(lone) in paths
    assert str(models / "a.glb") in paths
    assert str(models / "b.gltf") in paths
    assert str(nested / "c.glb") in paths
    assert not any(p.endswith("readme.txt") for p in paths)


def test_collect_openable_model_paths_skips_non_models(tmp_path: Path):
    img = tmp_path / "sky.hdr"
    img.write_bytes(b"hdr")
    assert collect_openable_model_paths([str(img)], allowed_exts=["glb"]) == []


def test_collect_openable_model_paths_respects_max_files(tmp_path: Path):
    folder = tmp_path / "many"
    folder.mkdir()
    for index in range(10):
        (folder / f"{index:02d}.glb").write_bytes(b"x")
    paths = collect_openable_model_paths(
        [str(folder)], allowed_exts=["glb"], max_files=3
    )
    assert len(paths) == 3
    assert DEFAULT_MAX_BATCH_OPEN >= 3
