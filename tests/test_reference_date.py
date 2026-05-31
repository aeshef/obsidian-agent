"""Разбор календарного дня из вопроса пользователя."""
from datetime import date

from planning_bot.services.reference_date import resolve_calendar_day_from_text


def test_resolve_iso():
    assert resolve_calendar_day_from_text(
        "логи за 2026-05-28", today=date(2026, 5, 31)
    ) == date(2026, 5, 28)


def test_resolve_n_days_ago_ru():
    assert resolve_calendar_day_from_text(
        "что я 3 дня назад делал по логам?", today=date(2026, 5, 31)
    ) == date(2026, 5, 28)


def test_resolve_yesterday():
    assert resolve_calendar_day_from_text(
        "вчера по логам", today=date(2026, 5, 31)
    ) == date(2026, 5, 30)
