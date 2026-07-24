# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from exhibit.open_errors import format_open_failure_message


class FakeMeshoptError(Exception):
    pass


def test_format_open_failure_prepare():
    msg = format_open_failure_message(
        "/tmp/hero.glb",
        FakeMeshoptError("bad"),
        meshopt_error_type=FakeMeshoptError,
    )
    assert msg == "Can't prepare hero.glb: bad"


def test_format_open_failure_open_with_reason():
    msg = format_open_failure_message("/tmp/a.glb", "nope")
    assert msg == "Can't open a.glb: nope"


def test_format_open_failure_open_plain():
    assert format_open_failure_message("/tmp/a.glb") == "Can't open a.glb"
    assert format_open_failure_message(None) == "Can't open Unknown"
