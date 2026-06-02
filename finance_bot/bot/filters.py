"""Aiogram filters for finance UI."""
from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import Message

from bot.menu_labels import fin_menu


class MenuText(Filter):
    """Match message text against messages.ru.yaml label (finance.menu.*)."""

    def __init__(self, key: str) -> None:
        self._key = key

    async def __call__(self, message: Message) -> bool:
        return (message.text or "").strip() == fin_menu(self._key)


class BadgeText(Filter):
    async def __call__(self, message: Message) -> bool:
        from bot.config_loader import get_badge_config, is_badge_enabled

        if not is_badge_enabled():
            return False
        label = (get_badge_config().get("ui") or {}).get("menu_button") or fin_menu("badge")
        return (message.text or "").strip() == label
