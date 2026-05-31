"""Regression: get_missing_fields category lookup (batch paste crash)."""
from __future__ import annotations

import pytest

from bot.services.categories import load_categories
from bot.services.transactions.core import get_missing_fields


@pytest.mark.asyncio
async def test_get_missing_fields_expense_category_no_import_error():
    """Was: ModuleNotFoundError: No module named 'bot.services.services'."""
    cats = load_categories("expense")
    assert cats, "expense categories must exist in config"
    sample_cat = cats[0]
    parsed = {
        "type": "expense",
        "amount": 508,
        "category": sample_cat,
        "account": "Т-Банк",
        "description": "завтрак",
    }
    # Unknown tg_id → account flagged missing, but must not crash on category import
    missing = await get_missing_fields(parsed, tg_id=0)
    assert isinstance(missing, dict)
    assert "category" not in missing
