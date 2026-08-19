"""Shared log-dump contract is source-agnostic."""
from __future__ import annotations

from datetime import datetime, timedelta

from shared.domain_messages import dmsg
from shared.query.log_dump import (
    assemble_log_dump,
    coverage_of,
    events_from_pairs,
    format_coverage,
    format_event_shares,
)
from shared.query.tally_shares import iso_compact


def test_coverage_warns_on_tail_not_source_start():
    t0 = datetime(2026, 7, 1, 8, 0, 0)
    matched = [t0 + timedelta(days=i) for i in range(31)]
    shown = matched[-10:]
    cov = coverage_of(
        requested_start=t0,
        requested_end=datetime(2026, 7, 31, 23, 59, 0),
        matched_ts=matched,
        shown_ts=shown,
        slice_kind="tail",
    )
    text = "\n".join(format_coverage(cov))
    assert "n=31" in text
    assert str(cov.n_shown) in text
    assert cov.slice_kind in text
    note = dmsg("log_dump", "slice_note", shown=10, total=31, kind="tail")
    assert note in text


def test_head_slice_marks_incomplete_end():
    t0 = datetime(2026, 8, 1, 9, 0, 0)
    matched = [t0 + timedelta(hours=i) for i in range(20)]
    shown = matched[:5]
    cov = coverage_of(
        requested_start=t0,
        requested_end=matched[-1],
        matched_ts=matched,
        shown_ts=shown,
        slice_kind="head",
    )
    text = "\n".join(format_coverage(cov))
    expected = dmsg(
        "log_dump",
        "incomplete_end",
        last=iso_compact(cov.shown_last),
        requested_end=iso_compact(cov.match_last),
    )
    assert expected in text


def test_assemble_puts_shares_before_rows():
    t0 = datetime(2026, 8, 1, 10, 0, 0)
    events = [(t0 + timedelta(minutes=5 * i), "Alpha" if i < 8 else "Beta") for i in range(10)]
    cov = coverage_of(
        requested_start=t0,
        requested_end=t0 + timedelta(hours=1),
        matched_ts=[e[0] for e in events],
        shown_ts=[e[0] for e in events[-3:]],
        slice_kind="tail",
    )
    shares = format_event_shares(events_from_pairs(events), column="app")
    out = assemble_log_dump(
        title="log",
        coverage=cov,
        shares=shares,
        rows=["tail-row-1", "tail-row-2", "tail-row-3"],
    )
    assert out.index("n=10") < out.index("tail-row-1")
    assert shares.split("\n", 1)[0] in out
    assert out.index(shares.split("\n", 1)[0]) < out.index("tail-row-1")
    assert "Alpha" in out


def test_snapshot_load_days_uses_distance_from_now_not_span():
    from datetime import date, datetime

    from shared.query.ts import snapshot_load_days

    now = datetime(2026, 8, 19, 12, 0, 0)
    n = snapshot_load_days(date(2026, 6, 1), now=now, floor=14, extra=3, cap=400)
    assert n == 82
    span_sized = snapshot_load_days(date(2026, 6, 1), now=now, floor=7 + 14, extra=3, cap=400)
    assert span_sized == 82
    assert snapshot_load_days(None, now=now, floor=14, cap=400) == 14


def test_coverage_n_matched_override_when_safety_capped():
    t0 = datetime(2026, 7, 1, 8, 0, 0)
    tail = [t0 + timedelta(days=i) for i in range(20, 31)]
    cov = coverage_of(
        requested_start=t0,
        requested_end=datetime(2026, 7, 31, 23, 59, 0),
        matched_ts=tail,
        shown_ts=tail[-5:],
        slice_kind="tail",
        n_matched=31,
    )
    text = "\n".join(format_coverage(cov))
    assert "n=31" in text
    expected = dmsg(
        "log_dump",
        "incomplete_start",
        first=iso_compact(cov.match_first),
        requested_start=iso_compact(cov.requested_start),
    )
    assert expected in text
