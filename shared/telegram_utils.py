"""Telegram message utilities (split long text, strip markdown)."""
from __future__ import annotations

import re

def _default_message_len() -> int:
    from shared.telegram.limits import max_message_chars

    return max_message_chars()


def split_message(text: str, max_len: int | None = None) -> list[str]:
    """Split long text into parts ≤ max_len (by paragraphs/lines/spaces)."""
    limit = max_len if max_len is not None else _default_message_len()
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        chunk = rest[:limit]
        boundary = max(chunk.rfind("\n\n"), chunk.rfind("\n"), chunk.rfind(" "))
        if boundary < limit // 2:
            boundary = limit
        parts.append(rest[:boundary].rstrip())
        rest = rest[boundary:].lstrip()
    return parts


def strip_telegram_markdown(text: str) -> str:
    """Strip typical Markdown that looks like noise in plain Telegram."""
    if not text:
        return text
    out = text.replace("**", "").replace("__", "")
    out = re.sub(r"(?m)^#{1,6}\s+", "", out)
    out = out.replace("`", "")
    return out
