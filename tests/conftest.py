# SPDX-License-Identifier: GPL-3.0-or-later
"""Pytest bootstrap: expose ``src/`` as the ``exhibit`` package."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if "exhibit" not in sys.modules:
    pkg = types.ModuleType("exhibit")
    pkg.__path__ = [str(SRC)]  # type: ignore[attr-defined]
    sys.modules["exhibit"] = pkg
