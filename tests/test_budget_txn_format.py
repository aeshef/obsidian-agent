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


def test_summary_includes_income_comments():
    rows = [
        _income("2026-07-10", 50000, "Зарплата", "ИТМО июль"),
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
    assert "ИТМО июль" in out
    assert "Доходы" in out or "income" in out.lower() or "комментарий" in out.lower()
    assert "Зарплата" in out


def test_query_filter_matches_description():
    rows = [
        _income("2026-07-10", 50000, "Зарплата", "ИТМО июль"),
        _income("2026-07-15", 20000, "Прочее", "другой источник"),
    ]
    matched = filter_rows_by_query(rows, "итмо")
    assert len(matched) == 1
    assert matched[0]["description"] == "ИТМО июль"
    out = format_txn_matches(matched, label="Jul", query="итмо")
    assert "ИТМО июль" in out
    assert "50,000" in out or "50000" in out


def test_query_no_match():
    rows = [_income("2026-07-10", 100, "Прочее", "foo")]
    assert filter_rows_by_query(rows, "итмо") == []
