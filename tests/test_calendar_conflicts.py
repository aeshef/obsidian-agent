"""Calendar slot conflict formatting."""
from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

from planning_bot.services.calendar_service import get_events_for_day_text


def test_same_slot_two_titles_shows_conflict():
    events = [
        {
            "date": "2026-06-05",
            "start": "15:00",
            "end": "16:00",
            "title": "Meeting A",
            "is_cancelled": False,
        },
        {
            "date": "2026-06-05",
            "start": "15:00",
            "end": "16:00",
            "title": "Meeting B",
            "is_cancelled": False,
        },
    ]
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "Calendar.json"
        p.write_text(
            json.dumps({"meta": {"last_updated": "2026-06-05T12:00:00"}, "events": events}),
            encoding="utf-8",
        )
        text = get_events_for_day_text(p, date(2026, 6, 5))
        assert "Meeting A" in text
        assert "Meeting B" in text
        assert text.upper().count("CONFLICT") + text.count("КОНФЛИКТ") >= 1
