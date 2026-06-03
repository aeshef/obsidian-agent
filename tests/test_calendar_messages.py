"""Calendar tool output must not be empty when pdmsg keys exist."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.calendar_service import get_events_for_day_text


def test_calendar_pdmsg_keys_non_empty():
    assert pdmsg("calendar_day_header", day="2026-06-01").strip()
    assert pdmsg("calendar_event_timed", date="2026-06-01", start="10:00", end="11:00", cancelled="", tag="", title="X").strip()


def test_get_events_for_day_not_blank_when_events_exist(tmp_path, monkeypatch):
    import json

    p = tmp_path / "cal.json"
    p.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "date": "2026-06-01",
                        "start": "14:00",
                        "end": "15:00",
                        "title": "Sync",
                        "is_allday": False,
                        "is_cancelled": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    # Ensure planning.calendar_* from domain_messages.yaml (repo config)
    out = get_events_for_day_text(p, date(2026, 6, 1))
    assert "Sync" in out
    assert "14:00" in out
    assert len(out.strip()) > 20
