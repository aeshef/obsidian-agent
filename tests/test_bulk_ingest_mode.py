from knowledge_bot.app.state import (
    bulk_record_saved,
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
