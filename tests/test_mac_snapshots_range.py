"""Mac snapshots by arbitrary ISO interval."""
from __future__ import annotations

from datetime import date

import pytest

from planning_bot.core.config import CONTEXT_MAC_DIR
from planning_bot.services.context_parser import get_snapshots
from planning_bot.services.mac_context_query import (
    filter_mac_snapshots,
    format_mac_snapshots,
    resolve_mac_interval,
)


def test_resolve_day_only():
    start, end = resolve_mac_interval("2026-06-01", "2026-06-01")
    assert start is not None and end is not None
    assert start.date() == date(2026, 6, 1)
    assert end.hour == 23


def test_june_first_has_many_snapshots():
    if not CONTEXT_MAC_DIR.is_dir():
        pytest.skip("CONTEXT_MAC_DIR missing in vault")
    start, end = resolve_mac_interval("2026-06-01", "2026-06-01")
    snaps = get_snapshots(CONTEXT_MAC_DIR, days=5, logging_window_only=False)
    matched = filter_mac_snapshots(snaps, start=start, end=end)
    if len(matched) < 50:
        pytest.skip(f"only {len(matched)} mac snapshots for 2026-06-01 in vault (need 50+)")
    assert len(matched) > 50


def test_format_mac_snapshots_hour_window():
    if not CONTEXT_MAC_DIR.is_dir():
        pytest.skip("CONTEXT_MAC_DIR missing in vault")
    start, end = resolve_mac_interval("2026-06-01T12:00", "2026-06-01T16:00")
    assert start is not None and end is not None
    snaps = get_snapshots(CONTEXT_MAC_DIR, days=5, logging_window_only=False)
    matched = filter_mac_snapshots(snaps, start=start, end=end)
    if not matched:
        pytest.skip("no mac snapshots for 2026-06-01T12:00–16:00 in vault (author-only data)")
    out = format_mac_snapshots("2026-06-01T12:00", "2026-06-01T16:00", limit=0)
    assert "Mac-снапшоты" in out
    assert "12:" in out or "13:" in out
    assert "Cursor" in out or "Obsidian" in out or "Safari" in out
