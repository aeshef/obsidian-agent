"""Attachment type by extension — from config, not hardcoded in handler."""
from __future__ import annotations

from pathlib import Path


def media_kind_for_path(path: str, *, extensions: dict[str, list[str]]) -> str:
    ext = Path(str(path)).suffix.lower()
    for kind, exts in extensions.items():
        if ext in exts:
            return kind
    return "file"
