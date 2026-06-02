from types import SimpleNamespace

from knowledge_bot.app.handlers.telegram_media_helpers import (
    ingest_limitation_text,
    is_video_document,
    telegram_file_too_big,
)


def test_is_video_document_by_mime():
    doc = SimpleNamespace(mime_type="video/mp4", file_name="clip.bin")
    assert is_video_document(doc)


def test_is_video_document_by_extension():
    doc = SimpleNamespace(mime_type="application/octet-stream", file_name="reel.MP4")
    assert is_video_document(doc)


def test_is_video_document_pdf_false():
    doc = SimpleNamespace(mime_type="application/pdf", file_name="doc.pdf")
    assert not is_video_document(doc)


def test_telegram_file_too_big():
    assert telegram_file_too_big(Exception("Telegram server says - Bad Request: file is too big"))
    assert not telegram_file_too_big(Exception("timeout"))


def test_ingest_limitation_text():
    summary = {"meta": {"telegram_file_too_big": True}, "derived": {"ocr_text": "x"}}
    routed = {"attachments": {"links": [], "files": ["Export/x.jpg"]}}
    text = ingest_limitation_text(summary, routed)
    assert text and "ASR" in text and "youtu.be" in text
    summary["derived"]["asr_text"] = "hello"
    text2 = ingest_limitation_text(summary, routed)
    assert text2 and "ASR" not in text2
