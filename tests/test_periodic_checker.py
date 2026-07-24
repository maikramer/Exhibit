# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural / light behaviour checks for PeriodicChecker (no display)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "periodic_checker.py"


def test_periodic_checker_module_defines_class():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    assert "PeriodicChecker" in names


def test_periodic_checker_has_run_stop_check():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    methods = {
        n.name
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {"run", "stop", "periodic_check"} <= methods


def test_window_imports_periodic_checker():
    window = (ROOT / "src" / "window.py").read_text(encoding="utf-8")
    assert "from .periodic_checker import PeriodicChecker" in window
    assert "class PeriodicChecker" not in window
