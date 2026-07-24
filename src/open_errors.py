# SPDX-License-Identifier: GPL-3.0-or-later
"""User-facing open/prepare error messages (no GTK)."""

from __future__ import annotations

import os
from typing import Any


def format_open_failure_message(
    filepath: str | None,
    reason: Any = None,
    *,
    meshopt_error_type: type | tuple[type, ...] | None = None,
    unknown_label: str = "Unknown",
    prepare_fmt: str = "Can't prepare {}: {}",
    open_reason_fmt: str = "Can't open {}: {}",
    open_fmt: str = "Can't open {}",
) -> str:
    """Build the toast / error-page string for a failed open."""
    name = os.path.basename(str(filepath)) if filepath else unknown_label
    if meshopt_error_type is not None and isinstance(reason, meshopt_error_type):
        return prepare_fmt.format(name, reason)
    if reason is not None:
        return open_reason_fmt.format(name, reason)
    return open_fmt.format(name)
