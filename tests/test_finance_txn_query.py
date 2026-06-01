"""Expense aggregation semantics (consumption filter)."""
from __future__ import annotations

from shared.finance.txn_query import format_spending_by_category


def test_spending_by_category_excludes_transfer_like_expense():
    rows = [
        {"type": "expense", "amount": 100, "category": "Еда/Вне дома"},
        {"type": "expense", "amount": 500, "category": "Перевод"},
        {"type": "income", "amount": 1000, "category": "Зарплата"},
    ]
    out = format_spending_by_category(rows, label="Test")
    assert "Еда/Вне дома" in out
    assert "100" in out
    assert "Перевод" not in out or "500" not in out
