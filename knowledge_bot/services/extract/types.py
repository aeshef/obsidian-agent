"""Extracted media/text bundle from knowledge ingest pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class VisionRateLimitError(Exception):
    """OpenRouter vision API returned HTTP 429."""


@dataclass
class ExtractedBundle:
    raw_text: str
    urls: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    url_text: str = ""
    pdf_text: str = ""
    ocr_text: str = ""
    vision_text: str | None = None
    asr_text: str = ""
    yt_transcript_text: str = ""

    def to_summary(self) -> dict[str, Any]:
        derived: dict[str, str] = {
            "url_text": self.url_text or "",
            "pdf_text": self.pdf_text or "",
            "ocr_text": self.ocr_text or "",
            "asr_text": self.asr_text or "",
            "vision_text": (self.vision_text or ""),
        }
        if self.yt_transcript_text:
            derived["yt_transcript_text"] = self.yt_transcript_text
        return {
            "raw_text": self.raw_text,
            "urls": list(self.urls or []),
            "meta": dict(self.meta or {}),
            "derived": derived,
        }
