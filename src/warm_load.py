# SPDX-License-Identifier: GPL-3.0-or-later
"""Warm-load holder helpers (cancel / release temps; no GTK)."""

from __future__ import annotations

from typing import Any, Callable


def new_warm_load_holder() -> dict[str, Any]:
    """Create the dict used by LoadMixin warm-load / tab cancel paths."""
    return {
        "ready": False,
        "cancelled": False,
        "finished": False,
        "_temps_released": False,
    }


def release_warm_holder_temps(
    holder: dict[str, Any] | None,
    *,
    cleanup_temp: Callable[[str | None], None],
    release_prepared: Callable[[str | None], None],
) -> bool:
    """
    Drop prepare temps owned by a cancelled/abandoned warm-load holder.

    Returns True if temps were released this call.
    """
    if not holder or holder.get("_temps_released"):
        return False
    if not holder.get("ready") or "ok" not in holder:
        return False
    holder["_temps_released"] = True
    _resolved, load_path, meshopt_temp = holder["ok"]
    cleanup_temp(meshopt_temp)
    if load_path != _resolved:
        release_prepared(load_path)
    return True


def cancel_warm_load_holder(holder: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Mark holder cancelled. Caller should then ``release_warm_holder_temps``.

    Returns the holder when cancel applied, else None.
    """
    if not holder or holder.get("finished"):
        return None
    holder["cancelled"] = True
    return holder
