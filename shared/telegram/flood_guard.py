"""Per-chat Telegram API throttling and RetryAfter handling."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Awaitable, Callable, TypeVar

from aiogram.exceptions import TelegramRetryAfter

log = logging.getLogger("shared.telegram.flood_guard")

_chat_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_last_call_mono: dict[int, float] = {}

T = TypeVar("T")


def _min_interval_sec() -> float:
    from shared.agent.platform_config import platform_int

    ms = platform_int("telegram", "min_send_interval_ms", default=900)
    return max(0.0, ms / 1000.0)


def _max_retries() -> int:
    from shared.agent.platform_config import platform_int

    return max(1, platform_int("telegram", "flood_retry_max", default=5))


async def guarded_telegram(chat_id: int, call: Callable[[], Awaitable[T]]) -> T:
    """Serialize and throttle Telegram calls per chat; sleep on RetryAfter."""
    interval = _min_interval_sec()
    retries = _max_retries()
    lock = _chat_locks[chat_id]
    async with lock:
        for attempt in range(retries):
            now = time.monotonic()
            last = _last_call_mono.get(chat_id, 0.0)
            wait = interval - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                result = await call()
                _last_call_mono[chat_id] = time.monotonic()
                return result
            except TelegramRetryAfter as e:
                delay = float(getattr(e, "retry_after", 1) or 1) + 0.25
                log.warning(
                    "telegram flood chat=%s attempt=%d retry_after=%.1fs",
                    chat_id,
                    attempt + 1,
                    delay,
                )
                if attempt + 1 >= retries:
                    raise
                await asyncio.sleep(delay)
    raise RuntimeError("guarded_telegram: retries exhausted")


async def send_message_guarded(bot, chat_id: int, text: str, **kwargs):
    return await guarded_telegram(
        chat_id,
        lambda: bot.send_message(chat_id, text, **kwargs),
    )


async def edit_message_text_guarded(bot, chat_id: int, message_id: int, text: str, **kwargs):
    return await guarded_telegram(
        chat_id,
        lambda: bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, **kwargs),
    )
