"""Transaction write context (badge enforce, account resolve)."""
from __future__ import annotations

from bot.services.transactions.core import merge_write_context


def test_merge_write_context_enforce_overrides_nlu():
    parsed = {"type": "expense", "account": "Кошелек", "category": "Еда/Вне дома", "amount": 142}
    ctx = {"account": "Meal Badge", "category": "Еда/Бейдж"}
    merge_write_context(parsed, ctx, enforce=True)
    assert parsed["account"] == "Meal Badge"
    assert parsed["category"] == "Еда/Бейдж"
    assert parsed["amount"] == 142


def test_merge_write_context_fallback_only_empty():
    parsed = {"type": "expense", "account": "Кошелек", "amount": 100}
    ctx = {"account": "Meal Badge", "category": "Еда/Бейдж"}
    merge_write_context(parsed, ctx, enforce=False)
    assert parsed["account"] == "Кошелек"
    assert parsed["category"] == "Еда/Бейдж"
