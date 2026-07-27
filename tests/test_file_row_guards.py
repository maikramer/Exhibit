# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural guards for FileRow cancel/drop path handling."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = ROOT / "src" / "widgets" / "file_row.py"


def test_file_row_open_finish_and_drop_guarded():
    src = ROW.read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "FileRow"
    )
    open_fn = next(
        n
        for n in cls.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "on_open_file_dialog_file_response"
    )
    drop_fn = next(
        n
        for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "on_drop_received"
    )
    open_body = ast.get_source_segment(src, open_fn)
    drop_body = ast.get_source_segment(src, drop_fn)
    assert open_body is not None and "open_finish" in open_body
    assert "except Exception" in open_body
    assert drop_body is not None
    assert "if not files" in drop_body
    assert "if not filepath" in drop_body
