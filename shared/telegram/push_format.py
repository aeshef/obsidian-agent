"""Unified styling for scheduled Telegram pushes (plain text, one visual language)."""
from __future__ import annotations

from shared.i18n import msg


def push_divider() -> str:
    return (msg("push", "divider") or "────────").strip()


def format_push(title: str, body: str, *, footer: str | None = None) -> str:
    """Envelope: title, divider, body[, footer]. Skips empty body."""
    title = (title or "").strip()
    body = (body or "").strip()
    if not body:
        return ""
    parts = [title, push_divider(), body] if title else [body]
    if footer and str(footer).strip():
        parts.extend(["", str(footer).strip()])
    return "\n".join(parts).strip()


def format_push_sections(
    title: str,
    sections: list[tuple[str, str]],
    *,
    footer: str | None = None,
) -> str:
    """Build a multi-section brief; empty section bodies are dropped."""
    blocks: list[str] = []
    for heading, text in sections:
        text = (text or "").strip()
        if not text:
            continue
        heading = (heading or "").strip()
        blocks.append(f"{heading}\n{text}" if heading else text)
    if not blocks:
        return ""
    return format_push(title, "\n\n".join(blocks), footer=footer)
