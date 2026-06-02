"""Regression: get_missing_fields category lookup (batch paste crash)."""
from __future__ import annotations

import pytest

from bot.services.categories import load_categories
from bot.services.transactions.core import get_missing_fields, infer_account_type, is_cash_wallet_name


def test_infer_account_type_from_config_hints():
    assert infer_account_type("Тинькофф карта") == "card"
    assert infer_account_type("Наличные дома") == "wallet"


def test_is_cash_wallet_name():
    assert is_cash_wallet_name("Наличные")
    assert not is_cash_wallet_name("Тинькофф")


@pytest.mark.asyncio
async def test_get_missing_fields_expense_category_no_import_error(finance_db):
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
