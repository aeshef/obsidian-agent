"""Transaction tool formatting includes comments and query filter."""
from __future__ import annotations

from shared.agent.budget import (
    filter_rows_by_query,
    format_txn_matches,
    format_txn_summary,
)


def _income(date: str, amount: float, category: str, description: str) -> dict:
    return {
        "type": "income",
        "date": date,
        "amount": amount,
        "category": category,
        "description": description,
    }


def test_summary_has_income_category_totals():
    rows = [
        _income("2026-07-10", 50000, "Зарплата", "Employer July"),
        _income("2026-07-15", 20000, "Прочее", "фриланс"),
        {
            "type": "expense",
            "date": "2026-07-12",
            "amount": 300,
            "category": "Еда",
            "description": "кофе",
        },
    ]
    out = format_txn_summary(rows, label="Jul")
    assert "Зарплата" in out
    assert "50 000" in out
    assert "Employer July" not in out


def test_query_filter_matches_description():
    rows = [
        _income("2026-07-10", 50000, "Зарплата", "Employer July"),
        _income("2026-07-15", 20000, "Прочее", "другой источник"),
    ]
    matched = filter_rows_by_query(rows, "employer")
    assert len(matched) == 1
    assert matched[0]["description"] == "Employer July"
    out = format_txn_matches(matched, label="Jul", query="employer")
    assert "Employer July" in out
    assert "50 000" in out or "50000" in out


def test_query_no_match():
    rows = [_income("2026-07-10", 100, "Прочее", "foo")]
    assert filter_rows_by_query(rows, "employer") == []


def test_query_matches_uses_requested_range_not_first_row():
    from datetime import datetime

    from shared.domain_messages import dmsg
    from shared.query.tally_shares import iso_compact

    rows = [_income("2026-07-20", 100, "Прочее", "foo")]
    requested_start = datetime(2026, 7, 1)
    requested_end = datetime(2026, 7, 31, 23, 59)
    out = format_txn_matches(
        rows,
        label="Jul",
        query="foo",
        requested_start=requested_start,
        requested_end=requested_end,
    )
    assert "2026-07-01" in out
    expected = dmsg(
        "log_dump",
        "incomplete_start",
        first=iso_compact(datetime(2026, 7, 20)),
        requested_start=iso_compact(requested_start),
    )
    assert expected in out
    assert "2026-07-20" in out
