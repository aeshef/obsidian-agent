"""Mac context series/snapshot must not use Health-only validators."""
from __future__ import annotations

from datetime import date

from planning_bot.services.context_parser import is_valid_mac_snapshot
from planning_bot.services.mac_context_query import format_mac_series
from planning_bot.services.snapshot_query import latest_per_calendar_day


def test_mac_snapshots_not_filtered_as_health():
    snaps = [
        {"ts": "2026-06-01T14:00", "app": "Safari", "focus": "Work", "battery_pct": 80},
        {"ts": "2026-06-02T12:00", "app": "Cursor", "focus": "Work", "battery_pct": 55},
    ]
    assert is_valid_mac_snapshot(snaps[0])
    daily = latest_per_calendar_day(
        snaps,
        is_valid=is_valid_mac_snapshot,
        score_fn=lambda s: 1 if is_valid_mac_snapshot(s) else -1,
    )
    assert date(2026, 6, 1) in daily
    assert daily[date(2026, 6, 1)]["app"] == "Safari"


def test_format_mac_series_from_snaps(monkeypatch):
    snaps = [
        {"ts": "2026-06-01T18:00", "app": "Safari", "focus": "Work", "battery_pct": 70},
        {"ts": "2026-06-02T19:00", "app": "Cursor", "focus": "Personal", "battery_pct": 40},
    ]

    def fake_load(*, max_days: int = 14):
        return snaps

    monkeypatch.setattr(
        "planning_bot.services.mac_context_query._load_mac_snaps",
        fake_load,
    )
    out = format_mac_series("2026-06-01", "2026-06-02")
    assert "Safari" in out
    assert "Cursor" in out
    assert "(нет Mac-снапшотов" not in out
