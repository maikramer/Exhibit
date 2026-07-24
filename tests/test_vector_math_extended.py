# SPDX-License-Identifier: GPL-3.0-or-later
"""Expanded vector_math coverage (parametrize-heavy)."""

from __future__ import annotations

import math

import pytest

from exhibit.vector_math import (
    p_dist,
    v_abs,
    v_add,
    v_cross,
    v_dot_p,
    v_mod,
    v_mul,
    v_norm,
    v_sub,
)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((0, 0), (0, 0), 0.0),
        ((0, 0), (3, 4), 5.0),
        ((1, 1, 1), (1, 1, 1), 0.0),
        ((0, 0, 0), (1, 0, 0), 1.0),
        ((-1, -1), (2, 3), 5.0),
        ((1.5, 2.5), (1.5, 2.5), 0.0),
        ((0, 0, 0, 0), (1, 2, 2, 4), 5.0),
        ((10, 0), (10, 0), 0.0),
        ((-3, 0, 0), (0, 0, 0), 3.0),
        ((1, 2, 3), (4, 6, 3), 5.0),
    ],
)
def test_p_dist_known(a, b, expected):
    assert p_dist(a, b) == pytest.approx(expected)


@pytest.mark.parametrize(
    "a,b",
    [
        ((0, 0), (0, 0, 0)),
        ((1,), (1, 2)),
        ((1, 2, 3, 4), (1, 2, 3)),
        ((), (1,)),
    ],
)
def test_p_dist_dim_mismatch(a, b):
    with pytest.raises(ValueError, match="same dimension"):
        p_dist(a, b)


@pytest.mark.parametrize(
    "v,expected",
    [
        ((0,), 0.0),
        ((3, 4), 5.0),
        ((0, 0, 0), 0.0),
        ((1, 0, 0), 1.0),
        ((-3, 4), 5.0),
        ((1, 2, 2), 3.0),
        ((2, 3, 6), 7.0),
        ((0.3, 0.4), 0.5),
    ],
)
def test_v_mod_known(v, expected):
    assert v_mod(v) == pytest.approx(expected)


@pytest.mark.parametrize(
    "v,expected",
    [
        ((-1, 2, -3), (1, 2, 3)),
        ((0, 0, 0), (0, 0, 0)),
        ((5, -5), (5, 5)),
        ((-0.5,), (0.5,)),
        ((1, -2, 3, -4), (1, 2, 3, 4)),
    ],
)
def test_v_abs(v, expected):
    assert v_abs(v) == expected


@pytest.mark.parametrize(
    "v",
    [
        (1, 0, 0),
        (0, 1, 0),
        (0, 0, 1),
        (3, 0, 4),
        (1, 1, 1),
        (-2, 0, 0),
        (0.1, 0.2, 0.3),
        (1, 2),
        (5, 12, 0),
        (0, 0, 0.5),
    ],
)
def test_v_norm_unit_length(v):
    n = v_norm(v)
    length = math.sqrt(sum(x * x for x in n))
    assert length == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize(
    "v",
    [
        (0, 0),
        (0, 0, 0),
        (0.0,),
        (0, 0, 0, 0),
        (1e-15, 0, 0),
        (0, -1e-13, 0),
    ],
)
def test_v_norm_near_zero(v):
    n = v_norm(v)
    assert all(abs(x) < 1e-9 for x in n)
    assert len(n) == len(v)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((0, 0), (0, 0), (0, 0)),
        ((1, 2), (3, 4), (4, 6)),
        ((-1, -2, -3), (1, 2, 3), (0, 0, 0)),
        ((0.5, 0.5), (0.5, -0.5), (1.0, 0.0)),
        ((1,), (2,), (3,)),
        ((1, 2, 3, 4), (4, 3, 2, 1), (5, 5, 5, 5)),
    ],
)
def test_v_add_cases(a, b, expected):
    assert v_add(a, b) == pytest.approx(expected)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((5, 5), (2, 1), (3, 4)),
        ((0, 0, 0), (1, 2, 3), (-1, -2, -3)),
        ((1, 1), (1, 1), (0, 0)),
        ((10,), (3,), (7,)),
        ((1.5, 2.5, 3.5), (0.5, 0.5, 0.5), (1.0, 2.0, 3.0)),
    ],
)
def test_v_sub_cases(a, b, expected):
    assert v_sub(a, b) == pytest.approx(expected)


@pytest.mark.parametrize(
    "v,s,expected",
    [
        ((1, 2, 3), 0, (0, 0, 0)),
        ((1, 2, 3), 1, (1, 2, 3)),
        ((1, 2, 3), -1, (-1, -2, -3)),
        ((2, 4), 0.5, (1.0, 2.0)),
        ((1,), 10, (10,)),
        ((1, -1, 2), 3, (3, -3, 6)),
        ((0.25, 0.5), 4, (1.0, 2.0)),
    ],
)
def test_v_mul_cases(v, s, expected):
    assert v_mul(v, s) == pytest.approx(expected)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((1, 2, 3), (4, 5, 6), (4, 10, 18)),
        ((0, 0), (9, 9), (0, 0)),
        ((-1, 2), (3, -4), (-3, -8)),
        ((1,), (7,), (7,)),
        ((2, 2, 2, 2), (1, 2, 3, 4), (2, 4, 6, 8)),
    ],
)
def test_v_dot_p_elementwise(a, b, expected):
    assert v_dot_p(a, b) == pytest.approx(expected)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
        ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
        ((1, 2, 3), (1, 2, 3), (0, 0, 0)),
        ((2, 0, 0), (0, 3, 0), (0, 0, 6)),
        ((1, 1, 0), (0, 1, 1), (1, -1, 1)),
    ],
)
def test_v_cross_known(a, b, expected):
    assert v_cross(a, b) == pytest.approx(expected)


@pytest.mark.parametrize(
    "a,b",
    [
        ((1, 0), (0, 1)),
        ((1, 0, 0, 0), (0, 1, 0, 0)),
        ((1,), (2,)),
        ((), ()),
        ((1, 2, 3, 4, 5), (1, 2, 3, 4, 5)),
    ],
)
def test_v_cross_rejects_non_3d(a, b):
    with pytest.raises(ValueError, match="3-dimensional"):
        v_cross(a, b)


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_v_cross_orthogonal_to_inputs(axis):
    a = [0.0, 0.0, 0.0]
    b = [0.0, 0.0, 0.0]
    a[axis] = 1.0
    b[(axis + 1) % 3] = 1.0
    c = v_cross(tuple(a), tuple(b))
    assert sum(x * y for x, y in zip(c, a)) == pytest.approx(0.0)
    assert sum(x * y for x, y in zip(c, b)) == pytest.approx(0.0)
