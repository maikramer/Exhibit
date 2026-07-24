# SPDX-License-Identifier: GPL-3.0-or-later
"""Anti-regression: session restore opens tabs sequentially and never
truncates the stored session while a batch is still loading.

Bug being pinned down: ``_open_model_paths`` used to start every warm load
at once. Only the last tab ended up selected/realized, so earlier tabs got
stuck on the loading page forever, and ``_persist_session_files`` (called on
each ``on_file_opened``) rewrote ``session-files`` with only the tabs that
had finished — destroying the saved session on every startup.
"""

from __future__ import annotations

import ast
import logging
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _install_stubs() -> None:
    """Stub gi / f3d / exhibit.widgets so LoadMixin imports headlessly."""
    if "gi" not in sys.modules:
        gi = types.ModuleType("gi")
        gi.require_version = lambda *a, **k: None

        class _Template:
            @staticmethod
            def Callback(_name=None):
                def deco(fn):
                    return fn

                return deco

        repo = types.ModuleType("gi.repository")
        repo.Gtk = types.SimpleNamespace(Template=_Template)
        repo.GLib = types.SimpleNamespace(
            SOURCE_REMOVE=False,
            SOURCE_CONTINUE=True,
            timeout_add=lambda *a, **k: 0,
            idle_add=lambda *a, **k: 0,
            Variant=lambda *a, **k: None,
        )
        repo.Adw = types.SimpleNamespace()
        repo.Gio = types.SimpleNamespace()
        gi.repository = repo
        sys.modules["gi"] = gi
        sys.modules["gi.repository"] = repo

    if "f3d" not in sys.modules:
        f3d = types.ModuleType("f3d")
        f3d.Engine = types.SimpleNamespace(get_readers_info=lambda: [])
        sys.modules["f3d"] = f3d

    if "exhibit.widgets" not in sys.modules:
        widgets = types.ModuleType("exhibit.widgets")

        class ViewerTab:  # placeholder for isinstance checks only
            pass

        widgets.ViewerTab = ViewerTab
        sys.modules["exhibit.widgets"] = widgets


_install_stubs()

from exhibit.window_load import LoadMixin  # noqa: E402


class FakeSettings:
    def __init__(self, booleans: dict, strv: dict):
        self._booleans = dict(booleans)
        self._strv = {k: list(v) for k, v in strv.items()}

    def get_boolean(self, key):
        return self._booleans[key]

    def get_strv(self, key):
        return list(self._strv.get(key, []))

    def set_strv(self, key, value):
        self._strv[key] = list(value)


class FakeTab:
    def __init__(self, filepath=None):
        self.filepath = filepath
        self._warm_load_holder = None


class FakeWindow(LoadMixin):
    def __init__(self, settings: FakeSettings):
        self.saved_settings = settings
        self.logger = logging.getLogger("test")
        self.toasts: list[str] = []
        self.tabs: list[FakeTab] = []
        self.load_calls: list[dict] = []

    def send_toast(self, message, timeout=2):
        self.toasts.append(message)

    def load_file(self, **kwargs):
        self.load_calls.append(kwargs)

    def _iter_tabs(self):
        return iter(self.tabs)

    def finish_load(self, filepath: str) -> None:
        """Simulate the tail of ``on_file_opened`` for a queued item."""
        self.tabs.append(FakeTab(filepath=filepath))
        self._persist_session_files()
        self._advance_open_queue()


def _window(session_files=(), restore=True):
    settings = FakeSettings(
        {"restore-session": restore},
        {"session-files": list(session_files)},
    )
    return FakeWindow(settings), settings


def _glbs(tmp_path: Path, count: int) -> list[str]:
    paths = []
    for i in range(count):
        path = tmp_path / f"model_{i}.glb"
        path.write_bytes(b"glTF")
        paths.append(str(path))
    return paths


def test_open_model_paths_starts_only_first(tmp_path):
    win, _ = _window()
    paths = _glbs(tmp_path, 3)
    win._open_model_paths(paths)
    assert [c["filepath"] for c in win.load_calls] == [paths[0]]
    assert win.load_calls[0].get("new_tab") is None
    assert win._pending_open_paths == paths[1:]


def test_advance_open_queue_preserves_order_and_uses_new_tab(tmp_path):
    win, _ = _window()
    paths = _glbs(tmp_path, 3)
    win._open_model_paths(paths)
    assert win._advance_open_queue() is True
    assert win._advance_open_queue() is True
    assert win._advance_open_queue() is False
    assert [c["filepath"] for c in win.load_calls] == paths
    assert all(c.get("new_tab") is True for c in win.load_calls[1:])


def test_open_model_paths_caps_batch(tmp_path):
    from exhibit.drop_paths import DEFAULT_MAX_BATCH_OPEN

    win, _ = _window()
    paths = _glbs(tmp_path, DEFAULT_MAX_BATCH_OPEN + 2)
    win._open_model_paths(paths)
    assert len(win._pending_open_paths) == DEFAULT_MAX_BATCH_OPEN - 1
    assert win.toasts  # user is told about the cap


def test_restore_session_opens_every_stored_path(tmp_path):
    paths = _glbs(tmp_path, 3)
    win, settings = _window(session_files=paths)
    win._restore_session_files()
    assert len(win.load_calls) == 1  # only the first starts right away
    # Drive the queue like successive on_file_opened calls would.
    while len(win.tabs) < len(paths):
        win.finish_load(win.load_calls[len(win.tabs)]["filepath"])
    assert [c["filepath"] for c in win.load_calls] == paths
    assert settings.get_strv("session-files") == paths


def test_persist_mid_restore_does_not_truncate_session(tmp_path):
    paths = _glbs(tmp_path, 2)
    win, settings = _window(session_files=paths)
    win._restore_session_files()
    assert win._pending_open_paths == paths[1:]

    # First model finished while the second is still queued: the stored
    # session must keep both entries (this used to shrink to one).
    win.finish_load(paths[0])
    assert settings.get_strv("session-files") == paths

    # Second model finishes: full list persisted.
    assert settings.get_strv("session-files") == paths
    assert [c["filepath"] for c in win.load_calls] == paths


def test_persist_skipped_while_warm_load_in_flight(tmp_path):
    paths = _glbs(tmp_path, 2)
    win, settings = _window(session_files=paths)
    loaded = FakeTab(filepath=paths[0])
    loading = FakeTab(filepath=None)
    loading._warm_load_holder = {"ready": False}
    win.tabs = [loaded, loading]
    win._persist_session_files()
    assert settings.get_strv("session-files") == paths


def test_persist_writes_all_loaded_tabs(tmp_path):
    paths = _glbs(tmp_path, 2)
    win, settings = _window(session_files=[paths[0]])
    win.tabs = [FakeTab(filepath=p) for p in paths]
    win._persist_session_files()
    assert settings.get_strv("session-files") == paths


def test_persist_noop_when_restore_disabled(tmp_path):
    paths = _glbs(tmp_path, 2)
    win, settings = _window(session_files=[paths[0]], restore=False)
    win.tabs = [FakeTab(filepath=p) for p in paths]
    win._persist_session_files()
    assert settings.get_strv("session-files") == [paths[0]]


def _method_source(name: str) -> ast.FunctionDef:
    src = (ROOT / "src" / "window_load.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    mixin = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "LoadMixin"
    )
    return next(
        n
        for n in mixin.body
        if isinstance(n, ast.FunctionDef) and n.name == name
    )


def _calls_in(fn: ast.FunctionDef) -> set[str]:
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def test_open_and_failure_paths_advance_the_queue():
    # Both completion paths must keep the batch moving, or a restore with a
    # broken file in the middle would stall the remaining tabs forever.
    assert "_advance_open_queue" in _calls_in(_method_source("on_file_opened"))
    assert "_advance_open_queue" in _calls_in(
        _method_source("on_file_not_opened")
    )


def test_open_model_paths_does_not_start_parallel_loads():
    fn = _method_source("_open_model_paths")
    for node in ast.walk(fn):
        assert not isinstance(node, (ast.For, ast.While)), (
            "_open_model_paths must not loop over load_file: parallel warm "
            "loads leave unselected tabs unrealized and stuck loading"
        )
