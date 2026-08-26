"""Hierarchical finance category filters (Еда → Еда/Вне дома)."""
from __future__ import annotations

from shared.finance.category_match import category_matches, normalize_category_query
from finance_bot.bot.services.txn_query import format_spending_by_category


def test_normalize_strips_glob_suffixes():
    assert normalize_category_query("Еда/*") == "еда"
    assert normalize_category_query("Еда/") == "еда"
    assert normalize_category_query("Еда*") == "еда"
    assert normalize_category_query("Еда") == "еда"


def test_parent_matches_children_and_glob():
    assert category_matches("Еда", "Еда/Вне дома")
    assert category_matches("Еда", "Еда/Продукты")
    assert category_matches("Еда/*", "Еда/Вне дома")
    assert category_matches("Еда/", "Еда/Продукты")
    assert category_matches("Еда", "Еда")
    assert not category_matches("Еда", "Транспорт")
    assert not category_matches("Еда/*", "Транспорт")


def test_format_spending_filters_parent_and_groups_by_day():
    rows = [
        {"type": "expense", "amount": 3546, "category": "Еда/Вне дома", "date": "2026-04-15"},
        {"type": "expense", "amount": 379, "category": "Еда/Продукты", "date": "2026-04-15"},
        {"type": "expense", "amount": 1298, "category": "Еда/Вне дома", "date": "2026-04-20"},
        {"type": "expense", "amount": 500, "category": "Транспорт", "date": "2026-04-15"},
        {"type": "expense", "amount": 100, "category": "Перевод", "date": "2026-04-15"},
    ]
    # Exact parent name used to yield "no expenses" when LLM passed Еда/* or looked for leaf «Еда».
    out_glob = format_spending_by_category(
        rows, label="Apr", category="Еда/*", group_by_day=True
    )
    assert "2026-04-15" in out_glob
    assert "3 925" in out_glob or "3,925" in out_glob or "3925" in out_glob
    assert "2026-04-20" in out_glob
    assert "Транспорт" not in out_glob
    assert "Перевод" not in out_glob

    out_parent = format_spending_by_category(rows, label="Apr", category="Еда")
    assert "Еда/Вне дома" in out_parent
    assert "Еда/Продукты" in out_parent
    assert "Транспорт" not in out_parent
