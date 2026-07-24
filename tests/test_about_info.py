# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from exhibit.about_info import (
    FORK_ISSUES,
    FORK_REPO,
    UPSTREAM_REPO,
    about_comments,
)


def test_about_urls():
    assert FORK_REPO.endswith("/maikramer/Exhibit")
    assert FORK_ISSUES == f"{FORK_REPO}/issues"
    assert UPSTREAM_REPO.endswith("/Nokse22/Exhibit")


def test_about_comments_mentions_fork_features():
    text = about_comments()
    assert "multi-tab" in text
    assert "session restore" in text
    assert "Split Compare" in text
    assert "turntable" in text


def test_desktop_keywords_include_split_compare():
    from pathlib import Path

    desktop = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "io.github.nokse22.Exhibit.desktop.in"
    ).read_text(encoding="utf-8")
    assert "split;" in desktop or "split-compare;" in desktop
    assert "compare;" in desktop
