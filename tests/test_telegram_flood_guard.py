"""Telegram flood guard tests."""
from __future__ import annotations

import asyncio

import pytest
from aiogram.exceptions import TelegramRetryAfter


def test_guarded_telegram_retries_after_flood(monkeypatch):
    from shared.telegram import flood_guard as fg

    monkeypatch.setattr(fg, "_min_interval_sec", lambda: 0.0)
    monkeypatch.setattr(fg, "_max_retries", lambda: 3)
    fg._last_call_mono.clear()

    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TelegramRetryAfter(method="sendMessage", message="retry", retry_after=0)
        return "ok"

    out = asyncio.run(fg.guarded_telegram(42, flaky))
    assert out == "ok"
    assert calls["n"] == 2
