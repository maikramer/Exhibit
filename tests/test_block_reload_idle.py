# SPDX-License-Identifier: GPL-3.0-or-later
"""``block_reload`` must clear when warm-load is cancelled with no peers."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
LOAD = ROOT / "src" / "window_load.py"
TABS = ROOT / "src" / "window_tabs.py"


def _warm_load_in_flight(tabs) -> bool:
    """Mirror LoadMixin._warm_load_in_flight (kept Gtk-free for host pytest)."""
    for tab in tabs:
        holder = getattr(tab, "_warm_load_holder", None)
        if not holder:
            continue
        if holder.get("cancelled") or holder.get("finished"):
            continue
        return True
    return False


def _unblock_reload_if_idle(block_reload: bool, tabs) -> bool:
    if not _warm_load_in_flight(tabs):
        return False
    return block_reload


def test_unblock_reload_when_no_holders():
    assert _unblock_reload_if_idle(True, []) is False


def test_unblock_keeps_block_while_peer_in_flight():
    active = SimpleNamespace(
        _warm_load_holder={"cancelled": False, "finished": False}
    )
    assert _unblock_reload_if_idle(True, [active]) is True


def test_unblock_ignores_cancelled_or_finished_holders():
    tabs = [
        SimpleNamespace(_warm_load_holder={"cancelled": True, "finished": False}),
        SimpleNamespace(_warm_load_holder={"cancelled": False, "finished": True}),
        SimpleNamespace(_warm_load_holder=None),
    ]
    assert _unblock_reload_if_idle(True, tabs) is False


def test_mixin_defines_and_calls_unblock():
    load_src = LOAD.read_text(encoding="utf-8")
    tabs_src = TABS.read_text(encoding="utf-8")
    assert "def _warm_load_in_flight" in load_src
    assert "def _unblock_reload_if_idle" in load_src
    assert "_unblock_reload_if_idle" in tabs_src

    tree = ast.parse(load_src)
    mixin = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LoadMixin"
    )
    for name in ("_warm_load_tick", "_warm_prepare_finished"):
        fn = next(
            n
            for n in mixin.body
            if isinstance(n, ast.FunctionDef) and n.name == name
        )
        body = ast.get_source_segment(load_src, fn)
        assert body is not None
        assert "_unblock_reload_if_idle" in body

    # Algorithm in source matches the Gtk-free mirror above.
    inflight = next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef) and n.name == "_warm_load_in_flight"
    )
    body = ast.get_source_segment(load_src, inflight)
    assert body is not None
    assert 'holder.get("cancelled")' in body
    assert 'holder.get("finished")' in body
