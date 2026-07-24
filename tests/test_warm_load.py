# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from exhibit.warm_load import (
    cancel_warm_load_holder,
    new_warm_load_holder,
    release_warm_holder_temps,
)


def test_new_warm_load_holder_defaults():
    holder = new_warm_load_holder()
    assert holder["ready"] is False
    assert holder["cancelled"] is False
    assert holder["finished"] is False
    assert holder["_temps_released"] is False


def test_cancel_warm_load_holder_skips_finished():
    holder = new_warm_load_holder()
    holder["finished"] = True
    assert cancel_warm_load_holder(holder) is None
    assert holder["cancelled"] is False

    active = new_warm_load_holder()
    assert cancel_warm_load_holder(active) is active
    assert active["cancelled"] is True


def test_release_warm_holder_temps_only_when_ready_ok():
    cleaned: list[str | None] = []
    released: list[str | None] = []

    holder = new_warm_load_holder()
    assert (
        release_warm_holder_temps(
            holder,
            cleanup_temp=cleaned.append,
            release_prepared=released.append,
        )
        is False
    )

    holder["ready"] = True
    holder["ok"] = ("/src/a.glb", "/tmp/prepared.glb", "/tmp/meshopt.tmp")
    assert (
        release_warm_holder_temps(
            holder,
            cleanup_temp=cleaned.append,
            release_prepared=released.append,
        )
        is True
    )
    assert cleaned == ["/tmp/meshopt.tmp"]
    assert released == ["/tmp/prepared.glb"]
    # Idempotent
    assert (
        release_warm_holder_temps(
            holder,
            cleanup_temp=cleaned.append,
            release_prepared=released.append,
        )
        is False
    )
    assert cleaned == ["/tmp/meshopt.tmp"]


def test_release_skips_release_prepared_when_same_path():
    released: list[str | None] = []
    holder = new_warm_load_holder()
    holder["ready"] = True
    holder["ok"] = ("/src/a.glb", "/src/a.glb", None)
    release_warm_holder_temps(
        holder,
        cleanup_temp=lambda _p: None,
        release_prepared=released.append,
    )
    assert released == []
