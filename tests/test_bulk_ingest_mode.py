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
