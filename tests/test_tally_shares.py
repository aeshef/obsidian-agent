"""Generic timestamped-category share tally (any log)."""
from __future__ import annotations

from datetime import datetime, timedelta

from shared.query.tally_shares import (
    format_tally,
    parse_timestamped_categories,
    tally_events,
)


def test_duration_shares_prefer_majority_app():
    t0 = datetime(2026, 8, 1, 10, 0, 0)
    events = []
    for i in range(10):
        events.append((t0 + timedelta(minutes=5 * i), "Alpha"))
    for i in range(10, 12):
        events.append((t0 + timedelta(minutes=5 * i), "Beta"))
    result = tally_events(events, column="app")
    assert result.mode == "duration"
    assert result.events == 12
    assert result.rows[0].value == "Alpha"
    assert result.rows[0].hour_share > 0.7
    body = format_tally(result, top_n=5)
    assert "Alpha" in body
    assert "hour_share" in body


def test_date_only_series_is_count_mode_not_hours():
    text = "date\tapp\n2026-08-01\tAlpha\n2026-08-02\tAlpha\n2026-08-03\tBeta\n"
    events, col = parse_timestamped_categories(text)
    assert col == "app"
    result = tally_events(events, column=col)
    assert result.mode == "count"
    assert result.rows[0].value == "Alpha"
    assert result.rows[0].count == 2


def test_parse_mac_like_tsv_without_header():
    text = (
        "2026-08-01T10:00:00\tAlpha\tfocus\t80\t\n"
        "2026-08-01T10:05:00\tAlpha\tfocus\t80\t\n"
        "2026-08-01T10:10:00\tBeta\tfocus\t79\t\n"
    )
    events, col = parse_timestamped_categories(text)
    assert len(events) == 3
    assert events[0][1] == "Alpha"
    assert col in ("value", "app")


def test_overnight_gap_is_capped():
    events = [
        (datetime(2026, 8, 1, 23, 50, 0), "Alpha"),
        (datetime(2026, 8, 2, 9, 0, 0), "Beta"),
        (datetime(2026, 8, 2, 9, 5, 0), "Beta"),
    ]
    result = tally_events(events, column="app")
    alpha = next(r for r in result.rows if r.value == "Alpha")
    assert alpha.hours < 1.0
