# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared openable extension lists (kept out of window.py to avoid import cycles)."""

from __future__ import annotations

import f3d

allowed_extensions: list[str] = []

for reader in f3d.Engine.get_readers_info():
    allowed_extensions += reader.extensions

# Ensure packed/external glTF stays openable even if a reader omits an alias.
for _ext in ("glb", "gltf"):
    if _ext not in allowed_extensions:
        allowed_extensions.append(_ext)

image_patterns = ["hdr", "exr", "png", "jpg", "pnm", "tiff", "bmp"]
