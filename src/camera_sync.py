# SPDX-License-Identifier: GPL-3.0-or-later
"""Peer-tab camera sync helpers (no GTK)."""

from __future__ import annotations

from typing import Any, Callable, Iterable


def iter_camera_sync_peers(
    tabs: Iterable[Any],
    *,
    source: Any,
    loaded_attr: str = "loaded",
    viewer_attr: str = "viewer",
    extras: Iterable[Any] | None = None,
) -> list[Any]:
    """Return viewers that should receive ``source``'s camera state."""
    peers: list[Any] = []
    for tab in tabs:
        if not getattr(tab, loaded_attr, False):
            continue
        viewer = getattr(tab, viewer_attr, None)
        if viewer is None or viewer is source:
            continue
        peers.append(viewer)
    if extras:
        for viewer in extras:
            if viewer is None or viewer is source or viewer in peers:
                continue
            peers.append(viewer)
    return peers


def apply_camera_state_to_peers(
    peers: Iterable[Any],
    state: Any,
    *,
    set_state: Callable[[Any, Any], None] | None = None,
    on_error: Callable[[Any, BaseException], None] | None = None,
) -> int:
    """
    Apply ``state`` to each peer viewer.

    Returns how many peers were updated successfully.
    """
    apply = set_state or (lambda viewer, value: viewer.set_camera_state(value))
    ok = 0
    for viewer in peers:
        try:
            apply(viewer, state)
            ok += 1
        except Exception as exc:  # noqa: BLE001 — peer may be mid-teardown
            if on_error is not None:
                on_error(viewer, exc)
    return ok
