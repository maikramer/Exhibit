# SPDX-License-Identifier: GPL-3.0-or-later
"""FileRow HDRI pick must enable skybox (parity with window.load_hdri)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = ROOT / "src" / "widgets" / "file_row.py"


def test_file_row_enables_skybox_on_pick():
    src = ROW.read_text(encoding="utf-8")
    assert "def _ensure_skybox_enabled" in src
    assert 'set_setting("hdri-skybox", True)' in src
    for method in (
        "def on_image_activated",
        "def on_open_file_dialog_file_response",
        "def on_drop_received",
    ):
        body = src.split(method, 1)[1].split("def ", 1)[0]
        assert "_ensure_skybox_enabled" in body


def test_file_row_delete_disables_skybox():
    src = ROW.read_text(encoding="utf-8")
    body = src.split("def on_delete_clicked", 1)[1].split("def ", 1)[0]
    assert "on_delete_skybox" in body
    assert "_ensure_skybox_disabled" in src
