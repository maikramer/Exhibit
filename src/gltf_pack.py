# gltf_pack.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pack external ``.gltf`` + URI resources into a self-contained GLB."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import tempfile
from typing import Any
from urllib.parse import unquote, urlparse

from .meshopt_decompress import MeshoptError, _align4, _append_bytes, _glb_bytes


def _decode_data_uri(uri: str) -> bytes:
    if not uri.startswith("data:"):
        raise MeshoptError(f"Not a data URI: {uri[:32]}")
    try:
        header, payload = uri.split(",", 1)
    except ValueError as exc:
        raise MeshoptError("Malformed data URI") from exc
    if ";base64" in header:
        try:
            return base64.b64decode(payload, validate=True)
        except Exception as exc:
            raise MeshoptError("Invalid base64 data URI") from exc
    return unquote(payload).encode("utf-8")


def _load_uri_bytes(base_dir: str, uri: str) -> bytes:
    if uri.startswith("data:"):
        return _decode_data_uri(uri)
    parsed = urlparse(uri)
    if parsed.scheme in ("http", "https"):
        raise MeshoptError(
            "Remote texture/buffer URIs are not supported "
            f"({parsed.scheme}://…)"
        )
    if parsed.scheme == "file":
        path = unquote(parsed.path)
    elif parsed.scheme:
        raise MeshoptError(f"Unsupported URI scheme: {parsed.scheme}")
    else:
        path = os.path.normpath(os.path.join(base_dir, unquote(uri)))
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise MeshoptError(f"Failed to read external glTF resource: {path}") from exc


def _guess_image_mime(uri: str, data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\xabKTX 20\xbb\r\n\x1a\n"):
        return "image/ktx2"
    mime, _ = mimetypes.guess_type(uri.split("?", 1)[0])
    if mime and mime.startswith("image/"):
        return mime
    return None


def pack_gltf_file(path: str) -> tuple[dict[str, Any], bytes]:
    """
    Load a ``.gltf`` JSON file and embed buffer/image URIs into one BIN chunk.

    Returns ``(gltf, bin_chunk)`` ready for GLB serialization. Meshopt / KTX2
    preparation runs afterward via ``prepare_glb_for_load``.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            gltf = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MeshoptError(f"Invalid glTF JSON: {path}") from exc
    if not isinstance(gltf, dict):
        raise MeshoptError(f"Invalid glTF root: {path}")

    base_dir = os.path.dirname(os.path.realpath(path))
    new_bin = bytearray()
    buffers = list(gltf.get("buffers") or [])
    if not buffers:
        gltf["buffers"] = [{"byteLength": 0}]
        return gltf, b""

    # Concatenate every buffer payload (external URI or data URI).
    buffer_base: list[int] = []
    for index, buffer_def in enumerate(buffers):
        if not isinstance(buffer_def, dict):
            raise MeshoptError(f"Invalid buffer entry {index}")
        uri = buffer_def.get("uri")
        if not uri:
            raise MeshoptError(
                "External .gltf packing requires buffer URIs "
                f"(buffer {index} is missing uri)"
            )
        payload = _load_uri_bytes(base_dir, str(uri))
        offset = _append_bytes(new_bin, payload)
        buffer_base.append(offset)

    views = gltf.setdefault("bufferViews", [])
    for view in views:
        if not isinstance(view, dict):
            continue
        bi = int(view.get("buffer", 0))
        if bi < 0 or bi >= len(buffer_base):
            raise MeshoptError(f"bufferView references invalid buffer {bi}")
        view["buffer"] = 0
        view["byteOffset"] = int(view.get("byteOffset", 0)) + buffer_base[bi]

    for image in gltf.get("images") or []:
        if not isinstance(image, dict):
            continue
        uri = image.get("uri")
        if not uri:
            continue
        payload = _load_uri_bytes(base_dir, str(uri))
        offset = _append_bytes(new_bin, payload)
        view_index = len(views)
        views.append(
            {
                "buffer": 0,
                "byteOffset": offset,
                "byteLength": len(payload),
            }
        )
        image.pop("uri", None)
        image["bufferView"] = view_index
        if "mimeType" not in image:
            mime = _guess_image_mime(str(uri), payload)
            if mime:
                image["mimeType"] = mime

    pad = _align4(len(new_bin)) - len(new_bin)
    if pad:
        new_bin.extend(b"\x00" * pad)

    gltf["buffers"] = [{"byteLength": len(new_bin)}]
    return gltf, bytes(new_bin)


def write_packed_gltf_temp(path: str) -> str:
    """Pack ``.gltf`` to a temporary self-contained ``.glb`` path."""
    gltf, bin_chunk = pack_gltf_file(path)
    fd, temp_path = tempfile.mkstemp(prefix="exhibit-gltf-", suffix=".glb")
    os.close(fd)
    try:
        with open(temp_path, "wb") as handle:
            handle.write(_glb_bytes(gltf, bin_chunk))
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return temp_path
