"""Fail-closed authorization for a personal Telegram bot."""
from __future__ import annotations

import os

from aiogram import BaseMiddleware
from aiogram.types import Update


def configured_owner_id() -> int:
    """Require a numeric Telegram user ID; usernames are not identities."""
    value = (os.environ.get("TELEGRAM_USER_ID") or "").strip()
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise RuntimeError("TELEGRAM_USER_ID must be a positive numeric user ID")
    return int(value)


class OwnerAccessMiddleware(BaseMiddleware):
    """Silently discard updates outside the owner's private chat."""

    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    async def __call__(self, handler, event, data):
        if not isinstance(event, Update):
            return None
        try:
            payload = event.event
        except LookupError:
            return None
        user = getattr(payload, "from_user", None)
        message = getattr(payload, "message", None)
        chat = getattr(payload, "chat", None) or getattr(message, "chat", None)
        if (
            user is None
            or user.is_bot
            or user.id != self.owner_id
            or chat is None
            or chat.type != "private"
            or chat.id != self.owner_id
        ):
            return None
        return await handler(event, data)
