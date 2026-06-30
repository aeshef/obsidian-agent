"""Тесты Health tools и snapshot_query."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from planning_bot.services.health_data import (
    export_health_daily_csv,
    format_health_anomalies,
    format_health_correlations,
    format_health_series,
    format_health_snapshot,
    format_health_summary,
)
from planning_bot.services.iphone_health_fields import (
    extract_raw_fields,
    is_valid_health_snapshot,
    normalize_raw_fields,
)
from planning_bot.services.snapshot_query import (
    latest_per_calendar_day,
    parse_range_params,
    resolve_snapshot_for_day,
    snap_calendar_day,
)


EXTENDED_BODY = """---
ts: 28.05.2026, 21:31
weight: 89.2
steps: 9050
heartbeat_still: 69
variability: 15.76
sleep: 28.05.2026, 02:42-28.05.2026, 09:44
Total Time Asleep:6 hours 46 minutes
Core for 4 hours and 7 minutes
---
"""


LINKEDIN_GARBAGE = """---
ts: 01.06.2026, 06:17
source: iphone
https: //www.linkedin.com/comm/premium/products/
unsubscribe: https://www.linkedin.com/job-alert-email-unsubscribe
---
"""

CSS_GARBAGE = """---
ts: 01.06.2026, 14:10
source: iphone
margin: 0;
padding: 9px !important;
display: none !important;
---
"""


def test_reject_non_health_email_bodies():
    for body in (LINKEDIN_GARBAGE, CSS_GARBAGE):
        snap = normalize_raw_fields(extract_raw_fields(body))
        assert snap is not None
        assert not is_valid_health_snapshot(snap)


def test_normalize_extended_health_email():
    raw = extract_raw_fields(EXTENDED_BODY)
    snap = normalize_raw_fields(raw)
    assert snap is not None
    assert is_valid_health_snapshot(snap)
    assert snap["weight_kg"] == pytest.approx(89.2)
    assert snap["resting_hr_bpm"] == 69
    assert snap["hrv_ms"] == pytest.approx(15.76)
    assert "sleep_interval" in snap
    assert "sleep_detail" in snap
    assert "Total Time Asleep" in snap["sleep_detail"]


SLEEP_DETAIL_MULTILINE_BODY = """---
ts: 02.06.2026, 23:43
source: iphone
sleep_interval: 2 июня 2026 г., 04:28-2 июня 2026 г., 10:23
sleep_detail: Total Time Asleep:5 hours 52 minutes
Asleep for 0 minutes
Awake for 0 hours and 2 minutes
Core for 3 hours and 9 minutes
Deep for 1 hours and 10 minutes
In Bed for 0 minutes
REM for 1 hours and 33 minutes
weight_kg: 89.1
steps: 10340
---
"""


def test_sleep_detail_multiline_stages():
    snap = normalize_raw_fields(extract_raw_fields(SLEEP_DETAIL_MULTILINE_BODY))
    assert snap is not None
    detail = snap["sleep_detail"]
    assert "Deep for 1 hours and 10 minutes" in detail
    assert "REM for 1 hours and 33 minutes" in detail
    from shared.analytics.sleep_parse import parse_sleep_detail

    parsed = parse_sleep_detail(detail)
    assert parsed["iphone_sleep_deep_min"] == 70
    assert parsed["iphone_sleep_rem_min"] == 93


def test_snapshot_query_per_day():
    snaps = [
        {"ts": "2026-05-27T10:00", "steps": 100},
        {"ts": "2026-05-27T23:00", "steps": 9000},
        {"ts": "2026-05-28T23:57", "steps": 9050},
    ]
    daily = latest_per_calendar_day(snaps)
    assert snap_calendar_day(daily[date(2026, 5, 27)]) == date(2026, 5, 27)
    assert daily[date(2026, 5, 27)]["steps"] == 9000
    snap, d = resolve_snapshot_for_day(snaps, date(2026, 5, 28))
    assert d == date(2026, 5, 28)
    assert snap["steps"] == 9050


def test_snapshot_query_ignores_garbage_same_day():
    snaps = [
        {"ts": "2026-06-02T15:34", "https": "//ozone.ru", "margin": "0"},
        {"ts": "2026-06-02T23:43", "steps": 10340, "resting_hr_bpm": 73, "sleep_interval": "2 июня"},
    ]
    daily = latest_per_calendar_day(snaps)
    assert daily[date(2026, 6, 2)]["steps"] == 10340


def test_parse_range_defaults():
    start, end = parse_range_params("", "", default_days=7, ref=date(2026, 6, 1))
    assert end == date(2026, 6, 1)
    assert (end - start).days == 6


def test_format_health_from_fixture_dir(tmp_path, monkeypatch):
    iphone_dir = tmp_path / "IPhone"
    iphone_dir.mkdir()
    snap = normalize_raw_fields(extract_raw_fields(EXTENDED_BODY))
    assert snap
    (iphone_dir / "2026-05-28, 21-31.txt").write_text(
        "---\n" + "\n".join(f"{k}: {v}" for k, v in snap.items()) + "\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "planning_bot.services.health_data.IPHONE_CONTEXT_DIR",
        iphone_dir,
    )
    out = format_health_snapshot("2026-05-28")
    assert "health_day: 2026-05-28" in out
    assert "9050" in out
    series = format_health_series("2026-05-28", "2026-05-28", ["steps"])
    assert "2026-05-28" in series
    assert "9050" in series
    fallback = format_health_series("2026-05-28", "2026-05-28", ["weight"])
    assert "89.2" in fallback
    assert "weight_kg" in fallback or "не найдены" in fallback
    summary = format_health_summary("2026-05-28", "2026-05-28")
    assert "сводка" in summary.lower() or "Агрегаты" in summary
    n, csv_path = export_health_daily_csv(tmp_path / "health_daily.csv")
    assert n == 1
    assert csv_path.exists()


def test_anomalies_and_correlations_smoke(tmp_path, monkeypatch):
    iphone_dir = tmp_path / "IPhone"
    iphone_dir.mkdir()
    for i, steps in enumerate([8000, 8200, 8500, 8700, 9000, 20000]):
        d = f"2026-05-{20 + i:02d}"
        body = f"---\nts: {d}, 23:00\nsteps: {steps}\nweight_kg: 88\n---\n"
        (iphone_dir / f"{d}, 23-00.txt").write_text(body, encoding="utf-8")
    monkeypatch.setattr(
        "planning_bot.services.health_data.IPHONE_CONTEXT_DIR",
        iphone_dir,
    )
    anom = format_health_anomalies(lookback_days=10, z_threshold=1.5)
    assert "календарных" in anom or "steps" in anom.lower() or "аномалий" in anom
    corr = format_health_correlations("2026-05-20", "2026-05-25", ["steps", "weight_kg"])
    assert "корреляц" in corr.lower() or "(" in corr


def test_planning_registry_tools(monkeypatch):
    from planning_bot.app.agent_tools import build_planning_registry
    from shared.capabilities.profile import clear_capabilities_cache

    monkeypatch.setenv("CAP_MODULE_PLANNING", "1")
    monkeypatch.setenv("CAP_CONNECTOR_APPLE_HEALTH", "1")
    monkeypatch.setenv("CAP_CONNECTOR_MAC_CONTEXT", "1")
    monkeypatch.setenv("CAP_CONNECTOR_APPLE_CALENDAR", "1")
    clear_capabilities_cache()

    reg = build_planning_registry()
    names = set(reg.names())
    assert "get_health_snapshot" in names
    assert "get_health_series" in names
    assert "get_mac_context" in names
    assert "get_daily_context" not in names
