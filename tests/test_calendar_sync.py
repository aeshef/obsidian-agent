"""Calendar sync structural parsing (append-only export blocks)."""
from __future__ import annotations

from planning_bot.tools.calendar_sync import (
    _extract_txt_timestamp,
    _merge,
    _parse_txt,
    _reconcile_existing,
)


def test_extract_txt_timestamp_uses_last_export_block():
    txt = """---
23 Apr 2026 at 17:52
---
24.04.2026 10:45 - 11:00 Meet
---
2 Jun 2026 at 03:19
---
03.06.2026 10:45 - 11:00 Летучка
"""
    assert _extract_txt_timestamp(txt) == "2026-06-02T03:19:00"


def test_reconcile_drops_phantoms_on_touched_days():
    existing = [
        {
            "id": "a1",
            "date": "2026-06-05",
            "start": "09:30",
            "end": "12:00",
            "title": "Breakfast",
            "is_cancelled": False,
        },
        {
            "id": "b2",
            "date": "2026-06-05",
            "start": "16:05",
            "end": "17:30",
            "title": "",
            "is_cancelled": False,
        },
    ]
    new_events = [
        {
            "date": "2026-06-05",
            "start": "12:00",
            "end": "13:00",
            "title": "Standup",
            "is_cancelled": False,
        },
    ]
    kept, dropped = _reconcile_existing(existing, new_events, "2026-06-05T18:20:00")
    assert dropped == 2
    assert kept == []


def test_parse_txt_drops_future_phantom_not_in_later_block():
    """Hourly exports omit cancelled future slots; older blocks must not keep them."""
    txt = """---
5 Jun 2026 at 15:20
---
05.06.2026 15:00 - 16:00 Morning standup
05.06.2026 16:05 - 17:30 
05.06.2026 18:00 - 21:00 School speakers
---
5 Jun 2026 at 16:20
---
05.06.2026 18:00 - 23:00 SHAD teachers
06.06.2026 11:00 - 15:30 Parents meeting
"""
    events = _parse_txt(txt)
    slots = {(e["date"], e["start"], e["end"], e.get("title")) for e in events}
    assert ("2026-06-05", "15:00", "16:00", "Morning standup") in slots
    assert ("2026-06-05", "18:00", "23:00", "SHAD teachers") in slots
    assert not any(s[1] == "16:05" for s in slots)
    assert not any(s[1] == "18:00" and s[2] == "21:00" for s in slots)


def test_parse_txt_keeps_double_booking_same_slot():
    txt = """---
5 Jun 2026 at 14:00
---
05.06.2026 15:00 - 16:00 Meeting A
05.06.2026 15:00 - 16:00 Meeting B
"""
    events = _parse_txt(txt)
    titles = {e["title"] for e in events if e["date"] == "2026-06-05"}
    assert titles == {"Meeting A", "Meeting B"}


def test_merge_keeps_overlapping_titles_same_slot():
    ev_a = {
        "date": "2026-06-05",
        "start": "15:00",
        "end": "16:00",
        "title": "Meeting A",
        "is_cancelled": False,
    }
    ev_b = {
        "date": "2026-06-05",
        "start": "15:00",
        "end": "16:00",
        "title": "Meeting B",
        "is_cancelled": False,
    }
    merged, added, _ = _merge([], [ev_a, ev_b])
    assert added == 2
    titles = {e["title"] for e in merged}
    assert titles == {"Meeting A", "Meeting B"}
