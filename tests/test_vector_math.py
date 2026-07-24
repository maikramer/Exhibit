# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from exhibit.vector_math import p_dist, v_add, v_cross, v_dot, v_mod, v_mul, v_norm, v_sub


def test_v_norm_unit():
    n = v_norm((3.0, 0.0, 4.0))
    assert n == pytest.approx((0.6, 0.0, 0.8))


def test_v_norm_zero():
    assert v_norm((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)


def test_v_add_sub_mul():
    assert v_add((1, 2, 3), (4, 5, 6)) == (5, 7, 9)
    assert v_sub((4, 5, 6), (1, 2, 3)) == (3, 3, 3)
    assert v_mul((1, 2, 3), 2) == (2, 4, 6)


def test_v_cross_and_mod():
    assert v_cross((1, 0, 0), (0, 1, 0)) == (0, 0, 1)
    assert v_mod((3, 4, 0)) == pytest.approx(5.0)


def test_v_dot_scalar():
    assert v_dot((1, 2, 3), (4, 5, 6)) == pytest.approx(32.0)


def test_p_dist():
    assert p_dist((0, 0, 0), (3, 4, 0)) == pytest.approx(5.0)
