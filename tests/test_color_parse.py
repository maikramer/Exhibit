# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from exhibit.color_parse import list_to_rgb, rgb_to_list


def test_rgb_to_list_rgb():
    assert rgb_to_list("rgb(255,128,0)") == (1.0, 128 / 255, 0.0)


def test_rgb_to_list_rgba_ignores_alpha():
    assert rgb_to_list("rgba(0,255,128,0.5)") == (0.0, 1.0, 128 / 255)


def test_rgb_to_list_float_channels():
    assert rgb_to_list("rgb(255.0, 0.0, 0.0)") == (1.0, 0.0, 0.0)


def test_rgb_to_list_rejects_junk():
    with pytest.raises(ValueError):
        rgb_to_list("red")
    with pytest.raises(ValueError):
        rgb_to_list("rgb(1,2)")


def test_list_to_rgb_roundtrip():
    assert rgb_to_list(list_to_rgb([1.0, 0.5, 0.0])) == (1.0, 127 / 255, 0.0)


def test_list_to_rgb_pads_short_sequences():
    assert list_to_rgb([1.0]) == "rgb(255,0,0)"
    assert list_to_rgb([]) == "rgb(0,0,0)"
    assert list_to_rgb(None) == "rgb(0,0,0)"
