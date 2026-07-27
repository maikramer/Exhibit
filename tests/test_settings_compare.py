# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from exhibit.settings_compare import (
    formats_entry_to_pattern,
    formats_pattern_matches,
    normalize_formats_pattern,
    preset_key_from_name,
    settings_values_equal,
)


def test_settings_values_equal_scalars():
    assert settings_values_equal(1, 1)
    assert not settings_values_equal(1, 2)
    assert settings_values_equal("a", "a")


def test_settings_values_equal_rgb_list_tuple():
    assert settings_values_equal([0.1, 0.2, 0.3], (0.1, 0.2, 0.3))
    assert settings_values_equal([1, 0, 0], [1.0, 0.0, 0.0])
    assert not settings_values_equal([1, 0, 0], [0, 1, 0])


def test_settings_values_equal_non_numeric_sequences():
    assert settings_values_equal(["a", "b"], ("a", "b"))
    assert not settings_values_equal(["a"], ["b"])


def test_formats_entry_to_pattern_comma_variants():
    assert formats_entry_to_pattern("glb, gltf") == r".*\.(glb|gltf)$"
    assert formats_entry_to_pattern("glb,gltf") == r".*\.(glb|gltf)$"
    assert formats_entry_to_pattern(".glb; .GLTF") == r".*\.(glb|gltf)$"
    assert formats_entry_to_pattern("") == ".*()"
    assert formats_entry_to_pattern("glb,gltf").count("(") == 1


def test_formats_pattern_matches_extension_not_path_substring():
    mech = r".*\.(step|stp|iges|igs|off|3ds)$"
    assert formats_pattern_matches(mech, "/models/part.off")
    assert not formats_pattern_matches(mech, "/office/model.glb")
    assert not formats_pattern_matches(mech, "/tmp/office.glb")
    assert formats_pattern_matches(".*(stl|3mf)", "/a/b/thing.STL")
    assert not formats_pattern_matches(".*(stl|3mf)", "/stl_cache/foo.glb")


def test_normalize_formats_pattern_upgrades_legacy():
    assert normalize_formats_pattern(".*(ply)") == r".*\.(ply)$"
    assert normalize_formats_pattern(r".*\.(ply)$") == r".*\.(ply)$"
    assert normalize_formats_pattern(".*()") == ".*()"


def test_preset_key_from_name_sanitizes_path_junk():
    assert preset_key_from_name("My Preset") == "my_preset"
    assert preset_key_from_name("../escape") == "escape"
    assert preset_key_from_name("a/b\\c") == "a_b_c"
    assert preset_key_from_name("   ") == "preset"
    assert "/" not in preset_key_from_name("../../x")
    assert "\\" not in preset_key_from_name("..\\x")
