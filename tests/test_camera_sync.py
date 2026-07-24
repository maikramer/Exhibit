# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from types import SimpleNamespace

from exhibit.camera_sync import apply_camera_state_to_peers, iter_camera_sync_peers


def test_iter_camera_sync_peers_skips_source_and_unloaded():
    source = object()
    peer = object()
    tabs = [
        SimpleNamespace(loaded=True, viewer=source),
        SimpleNamespace(loaded=False, viewer=peer),
        SimpleNamespace(loaded=True, viewer=peer),
        SimpleNamespace(loaded=True, viewer=None),
    ]
    assert iter_camera_sync_peers(tabs, source=source) == [peer]


def test_iter_camera_sync_peers_includes_extras():
    source = object()
    peer = object()
    extra = object()
    tabs = [SimpleNamespace(loaded=True, viewer=peer)]
    assert iter_camera_sync_peers(
        tabs, source=source, extras=[extra, source, peer, None]
    ) == [peer, extra]


def test_apply_camera_state_to_peers_counts_ok_and_errors():
    ok_viewer = SimpleNamespace(states=[])
    bad_viewer = SimpleNamespace()

    def set_state(viewer, state):
        if viewer is bad_viewer:
            raise RuntimeError("boom")
        viewer.states.append(state)

    errors: list[str] = []
    count = apply_camera_state_to_peers(
        [ok_viewer, bad_viewer],
        {"pos": 1},
        set_state=set_state,
        on_error=lambda _v, exc: errors.append(str(exc)),
    )
    assert count == 1
    assert ok_viewer.states == [{"pos": 1}]
    assert errors == ["boom"]
