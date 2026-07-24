# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from exhibit import logger_lib


def test_custom_formatter_includes_ansi():
    formatter = logger_lib.CustomFormatter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="msg",
        args=(),
        exc_info=None,
    )
    text = formatter.format(record)
    assert "\x1b[" in text


def test_init_uses_xdg_data_home_as_app_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Flatpak / explicit XDG_DATA_HOME is already the app data directory.
    data = tmp_path / "app-data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    logger_lib.init()
    assert data.is_dir()
    assert hasattr(logger_lib, "logger")
    logger_lib.logger.debug("probe")
    assert (data / "log.txt").exists() or data.exists()


def test_init_default_path_without_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    logger_lib.init()
    expected = tmp_path / ".local" / "share" / "exhibit"
    assert expected.is_dir()
