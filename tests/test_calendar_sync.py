"""Calendar sync structural parsing (append-only export blocks)."""
from __future__ import annotations

from planning_bot.tools.calendar_sync import (
    _extract_txt_timestamp,
    _merge,
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


def test_reconcile_drops_future_phantom_keeps_past_slot():
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
    kept, dropped = _reconcile_existing(existing, new_events, "2026-06-05T11:15:00")
    assert dropped == 1
    titles = {e["title"] for e in kept}
    assert "Breakfast" in titles
    assert "" not in titles


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
