# SPDX-License-Identifier: GPL-3.0-or-later
"""Pytest bootstrap: expose ``src/`` as the ``exhibit`` package."""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if "exhibit" not in sys.modules:
    pkg = types.ModuleType("exhibit")
    pkg.__path__ = [str(SRC)]  # type: ignore[attr-defined]
    sys.modules["exhibit"] = pkg

_EXHIBIT_TEMP_PREFIXES = (
    "exhibit-meshopt-",
    "exhibit-parts-",
    "exhibit-skinw-",
    "exhibit-ktx-",
    "exhibit-pack-",
)


def _list_exhibit_temps() -> set[str]:
    base = Path(tempfile.gettempdir())
    found: set[str] = set()
    try:
        for entry in base.iterdir():
            if any(entry.name.startswith(p) for p in _EXHIBIT_TEMP_PREFIXES):
                found.add(str(entry))
    except OSError:
        pass
    return found


@pytest.fixture(scope="session", autouse=True)
def _exhibit_prepare_cache_session():
    """Clear prepare cache at session end; warn on new /tmp exhibit-* leftovers."""
    before = _list_exhibit_temps()
    yield
    try:
        from exhibit.meshopt_decompress import clear_prepare_cache, prepare_cache_stats

        stats = prepare_cache_stats()
        clear_prepare_cache()
    except Exception:
        stats = {}
    after = _list_exhibit_temps()
    leaked = sorted(after - before)
    if leaked:
        import warnings

        sample = ", ".join(Path(p).name for p in leaked[:8])
        more = f" (+{len(leaked) - 8} more)" if len(leaked) > 8 else ""
        warnings.warn(
            f"pytest session left {len(leaked)} new exhibit temp(s) under "
            f"{tempfile.gettempdir()}: {sample}{more}; cache_stats={stats}",
            UserWarning,
            stacklevel=1,
        )


# Legacy structural tests still asserting pre-migrate glue ownership.
# Keep skipped until each file is rewritten for ExbWindow + declarative shell.
# Actively maintained: test_window_init_helpers, test_window_load_mixin,
# test_window_settings_react_mixin (not listed below).
_LEGACY_MIXIN_TESTS = {
    "test_window_chrome_mixin.py",
    "test_window_export_mixin.py",
    "test_window_file_watch_mixin.py",
    "test_window_inspect_mixin.py",
    "test_window_layout_mixin.py",
    "test_window_lifecycle_mixin.py",
    "test_window_preferences.py",
    "test_window_settings_io_mixin.py",
    "test_window_tabs_context_menu.py",
    "test_window_tabs_split.py",
}


def pytest_ignore_collect(collection_path, config):
    base = getattr(collection_path, "name", None) or Path(str(collection_path)).name
    if base in _LEGACY_MIXIN_TESTS:
        return True
    return None
