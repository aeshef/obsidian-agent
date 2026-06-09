from knowledge_bot.app.bulk_helpers import bulk_ack_every, bulk_should_skip_save
from knowledge_bot.app.state import (
    bulk_record_saved,
    bulk_take_processing_ack,
    is_bulk_ingest,
    set_bulk_ingest,
)


def test_bulk_ingest_toggle_and_stats():
    uid = 4242
    set_bulk_ingest(uid, True)
    assert is_bulk_ingest(uid)
    bulk_record_saved(uid)
    bulk_record_saved(uid)
    stats = set_bulk_ingest(uid, False)
    assert stats["saved"] == 2
    assert not is_bulk_ingest(uid)


def test_bulk_processing_ack_once():
    uid = 777
    set_bulk_ingest(uid, True)
    assert bulk_take_processing_ack(uid)
    assert not bulk_take_processing_ack(uid)
    set_bulk_ingest(uid, False)


def test_bulk_should_skip_empty_render():
    assert bulk_should_skip_save({}, {}, "")


def test_bulk_should_not_skip_with_ocr(monkeypatch):
    monkeypatch.delenv("BULK_ACK_EVERY", raising=False)
    routed = {"attachments": {"files": [], "links": []}, "raw_text": ""}
    summary = {"derived": {"ocr_text": "hello"}}
    assert not bulk_should_skip_save(routed, summary, "# Note\n\nhello")


def test_bulk_ack_every_from_env(monkeypatch):
    monkeypatch.setenv("BULK_ACK_EVERY", "5")
    assert bulk_ack_every() == 5
