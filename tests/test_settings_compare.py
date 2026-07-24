# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from exhibit.settings_compare import settings_values_equal


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
