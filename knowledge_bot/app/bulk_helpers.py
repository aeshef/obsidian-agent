"""Bulk ingest helpers (no aiogram imports — testable in isolation)."""
from __future__ import annotations

import os
from typing import Any

_DERIVED_KEYS = (
    "ocr_text",
    "asr_text",
    "pdf_text",
    "vision_text",
    "yt_transcript_summary",
    "yt_transcript_text",
)


def bulk_ack_every() -> int:
    raw = (os.environ.get("BULK_ACK_EVERY") or "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def bulk_should_skip_save(
    routed: dict[str, Any],
    summary_obj: dict[str, Any],
    rendered: str,
) -> bool:
    """Skip empty ingest (e.g. undownloaded large video with no caption/ASR)."""
    if not (rendered or "").strip():
        return True
    derived = summary_obj.get("derived") or {}
    if any((derived.get(k) or "").strip() for k in _DERIVED_KEYS):
        return False
    attachments = routed.get("attachments") or {}
    if attachments.get("files") or attachments.get("links"):
        return False
    raw = (routed.get("raw_text") or summary_obj.get("raw_text") or "").strip()
    return not raw
