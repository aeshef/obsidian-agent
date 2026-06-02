"""Create aiogram Bot with optional Local Bot API (TELEGRAM_API_BASE)."""
from __future__ import annotations

import os

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer


def telegram_api_base() -> str:
    return (os.environ.get("TELEGRAM_API_BASE") or "https://api.telegram.org").rstrip("/")


def is_local_telegram_api() -> bool:
    base = telegram_api_base()
    if base.rstrip("/") == "https://api.telegram.org":
        return False
    return os.environ.get("TELEGRAM_LOCAL", "1") not in ("0", "false", "False")


def create_bot(token: str, *, parse_mode=None) -> Bot:
    """Bot session: Local Bot API when TELEGRAM_API_BASE != api.telegram.org."""
    base = telegram_api_base()
    session = None
    if is_local_telegram_api():
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(base, is_local=True),
        )
    return Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=parse_mode),
    )
