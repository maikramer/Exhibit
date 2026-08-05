# SPDX-License-Identifier: GPL-3.0-or-later
"""ExbDirection index ↔ WindowSettings up string mapping (no gi import)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src" / "window_settings_ui.py"
GLOBAL_H = ROOT / "libexhibit" / "exb-global.h"


def _load_up_maps() -> tuple[dict[int, str], dict[str, int]]:
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    n_to_s: dict[int, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "up_dir_n_to_string":
                n_to_s = ast.literal_eval(node.value)
    assert n_to_s, "up_dir_n_to_string not found"
    s_to_n = {v: k for k, v in n_to_s.items()}
    return n_to_s, s_to_n


def test_up_dir_matches_exb_direction_order():
    n_to_s, s_to_n = _load_up_maps()
    assert n_to_s[0] == "+X"
    assert n_to_s[1] == "-X"
    assert n_to_s[2] == "+Y"
    assert n_to_s[3] == "-Y"
    assert n_to_s[4] == "+Z"
    assert n_to_s[5] == "-Z"
    assert s_to_n["+Y"] == 2
    header = GLOBAL_H.read_text(encoding="utf-8")
    # Declaration order in the enum must stay aligned with the map.
    pos = header.index("typedef enum")
    chunk = header[pos : pos + 280]
    assert chunk.index("POSITIVE_X") < chunk.index("NEGATIVE_X") < chunk.index(
        "POSITIVE_Y"
    )
