"""Aiogram middleware helpers."""
from __future__ import annotations

from aiogram import BaseMiddleware


class InjectMiddleware(BaseMiddleware):
    """Injects fixed keyword arguments into handler `data` (e.g. planning bot instance)."""

    def __init__(self, **injections):
        self.injections = injections

    async def __call__(self, handler, event, data):
        data.update(self.injections)
        return await handler(event, data)
