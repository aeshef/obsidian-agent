"""Auto-detect badge batch without badge menu."""
from __future__ import annotations

from unittest.mock import patch

from bot.handlers.badge import infer_badge_spend_text, parsed_expenses_are_badge


def test_infer_badge_spend_text_from_kr_lines():
    text = "\n".join(
        [
            "вчера бейдж КР: Кафе Альфа 4 этаж (вендомат) 142 ₽",
            "вчера бейдж КР: БЦ Пример: Столовая Бета (фудкорт) 290 ₽",
        ]
    )
    assert infer_badge_spend_text(text) is True


def test_infer_badge_spend_text_rejects_regular_expense():
    assert infer_badge_spend_text("кофе 350 вендомат") is False


def test_infer_badge_spend_text_when_badge_disabled_in_yaml():
    with patch("bot.handlers.badge.is_badge_enabled", return_value=False):
        assert infer_badge_spend_text("бейдж КР: кофе 400") is True


def test_parsed_expenses_are_badge_by_category():
    parsed = [
        {"type": "expense", "category": "Еда/Бейдж", "amount": 142},
        {"type": "expense", "category": "Еда/Бейдж", "amount": 290},
    ]
    with patch("bot.handlers.badge.badge_category_name", return_value="Еда/Бейдж"):
        assert parsed_expenses_are_badge(parsed) is True


def test_transaction_uses_badge_by_category_only():
    from bot.handlers.badge import transaction_uses_badge

    parsed = {"type": "expense", "category": "Еда/Бейдж", "account": "Кошелек"}
    with patch("bot.handlers.badge.badge_category_name", return_value="Еда/Бейдж"):
        assert transaction_uses_badge(parsed, badge_mode=False) is True
