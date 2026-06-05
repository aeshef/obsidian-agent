"""Media/text extraction for knowledge ingest."""
from __future__ import annotations

from knowledge_bot.services.extract.pipeline import extract_from_path
from knowledge_bot.services.extract.web import simple_from_text
from knowledge_bot.services.extract.youtube import download_via_ytdlp, fetch_youtube_transcript

__all__ = [
    "download_via_ytdlp",
    "extract_from_path",
    "fetch_youtube_transcript",
    "simple_from_text",
]
