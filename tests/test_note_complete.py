"""Integration: note_complete pipeline building blocks (no LLM)."""
from __future__ import annotations

from types import SimpleNamespace

from knowledge_bot.app.handlers.note_complete.helpers import collect_urls
from knowledge_bot.services.extract.web import simple_from_text


def test_simple_from_text_extracts_url():
    bundle = simple_from_text("Смотри https://example.com/page и комментарий")
    assert "https://example.com/page" in bundle.urls
    assert "example.com" in bundle.raw_text


def test_extracted_bundle_to_summary():
    bundle = simple_from_text("hello")
    summary = bundle.to_summary()
    assert summary["raw_text"] == "hello"
    assert "derived" in summary
    assert set(summary["derived"]) >= {"ocr_text", "asr_text", "url_text", "pdf_text", "vision_text"}


def test_collect_urls_from_text_and_entities():
    bundle = simple_from_text("https://example.org/a")
    url_b = "https://example.org/b"
    msg = SimpleNamespace(
        text=url_b,
        caption=None,
        entities=[SimpleNamespace(type="url", offset=0, length=len(url_b))],
        caption_entities=None,
    )
    urls = collect_urls(bundle, [msg])
    assert "https://example.org/a" in urls
    assert url_b in urls
