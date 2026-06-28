"""Tests for sleep_detail parsing."""
from __future__ import annotations

from shared.analytics.sleep_parse import parse_sleep_detail, sleep_ratios


def test_parse_sleep_hours_and_stages():
    detail = """Total Time Asleep:6 hours 46 minutes
Deep for 1 hours and 20 minutes
REM for 1 hours and 45 minutes
Core for 3 hours and 41 minutes
Awake for 12 minutes"""
    out = parse_sleep_detail(detail)
    assert abs(out["iphone_sleep_hours"] - (6 + 46 / 60)) < 0.01
    assert out["iphone_sleep_deep_min"] == 80
    assert out["iphone_sleep_rem_min"] == 105
    assert out["iphone_sleep_core_min"] == 221
    assert out["iphone_sleep_awake_min"] == 12


def test_sleep_ratios():
    row = {
        "iphone_sleep_hours": 7.0,
        "iphone_sleep_deep_min": 70.0,
        "iphone_sleep_rem_min": 90.0,
    }
    ratios = sleep_ratios(row)
    assert abs(ratios["iphone_sleep_deep_ratio"] - 70 / 420) < 1e-6
    assert abs(ratios["iphone_sleep_rem_ratio"] - 90 / 420) < 1e-6
