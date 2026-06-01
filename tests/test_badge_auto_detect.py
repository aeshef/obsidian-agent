"""Auto-detect badge batch without badge menu."""
from __future__ import annotations

from unittest.mock import patch

from bot.handlers.badge import infer_badge_spend_text, parsed_expenses_are_badge


def test_infer_badge_spend_text_from_kr_lines():
    text = "\n".join(
        [
            "бейдж КР: Морозов Го!Поедим 4 этаж (вендомат) 142 ₽",
            "бейдж КР: Деловой квартал: Сырный ХАЙП (фудкорт) 290 ₽",
        ]
    )
    with patch("bot.handlers.badge.is_badge_enabled", return_value=True):
        assert infer_badge_spend_text(text) is True


def test_infer_badge_spend_text_rejects_regular_expense():
    with patch("bot.handlers.badge.is_badge_enabled", return_value=True):
        assert infer_badge_spend_text("кофе 350 вендомат") is False


def test_parsed_expenses_are_badge_by_category():
    parsed = [
        {"type": "expense", "category": "Еда/Бейдж", "amount": 142},
        {"type": "expense", "category": "Еда/Бейдж", "amount": 290},
    ]
    with patch("bot.handlers.badge.is_badge_enabled", return_value=True):
        with patch("bot.handlers.badge.BadgeTracker") as bt:
            bt.return_value.category = "Еда/Бейдж"
            assert parsed_expenses_are_badge(parsed) is True
