"""Calendar retention: detail window + monthly archive + txt compact."""
from __future__ import annotations

from datetime import date

from planning_bot.services.calendar_retention import (
    apply_retention,
    build_monthly_rollups,
    compact_calendar_txt,
    detail_cutoff,
)


def test_detail_cutoff_three_months():
    assert detail_cutoff(date(2026, 6, 15)) == date(2026, 4, 1)


def test_apply_retention_moves_old_events():
    data = {
        "events": [
            {"date": "2024-01-10", "start": "10:00", "end": "11:00", "title": "Old"},
            {"date": "2026-06-10", "start": "10:00", "end": "11:00", "title": "New"},
        ],
        "meta": {},
    }
    out, moved, kept = apply_retention(data, anchor=date(2026, 6, 15))
    assert moved == 1
    assert kept == 1
    assert len(out["events"]) == 1
    assert out["events"][0]["title"] == "New"
    assert out["archive"]["monthly"]


def test_build_monthly_rollups_minutes():
    events = [
        {"date": "2024-02-01", "start": "10:00", "end": "11:30", "title": "A"},
        {"date": "2024-02-02", "start": "10:00", "end": "10:30", "title": "B"},
    ]
    rows = build_monthly_rollups(events)
    assert rows[0]["month"] == "2024-02"
    assert rows[0]["meeting_count"] == 2
    assert rows[0]["meeting_minutes"] == 120


def test_compact_calendar_txt_drops_old_lines():
    txt = """---
2 Jun 2026 at 03:19
---
01.01.2024 10:00 - 11:00 Old meet
03.06.2026 10:00 - 11:00 Recent
"""
    compacted, dropped = compact_calendar_txt(txt, anchor=date(2026, 6, 15))
    assert dropped == 1
    assert "2024" not in compacted
    assert "03.06.2026" in compacted
