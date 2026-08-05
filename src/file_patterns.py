# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared openable extension lists (kept out of window.py to avoid import cycles)."""

from __future__ import annotations

allowed_extensions: list[str] = []

try:
    import f3d

    for reader in f3d.Engine.get_readers_info():
        allowed_extensions += reader.extensions
except Exception:
    try:
        from gi.repository import Exb

        allowed_extensions = [e for e in Exb.get_allowed_extensions()]
    except Exception:
        allowed_extensions = [
            "glb",
            "gltf",
            "obj",
            "stl",
            "fbx",
            "ply",
            "3ds",
            "usd",
            "usda",
            "usdc",
            "3mf",
            "step",
            "stp",
            "iges",
            "igs",
            "off",
        ]

# Ensure packed/external glTF stays openable even if a reader omits an alias.
for _ext in ("glb", "gltf"):
    if _ext not in allowed_extensions:
        allowed_extensions.append(_ext)

image_patterns = ["hdr", "exr", "png", "jpg", "pnm", "tiff", "bmp"]
