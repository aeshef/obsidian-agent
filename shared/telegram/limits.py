"""Telegram API limits — from config/agent/platform.yaml."""
from __future__ import annotations

from shared.agent.platform_config import platform_int


def max_message_chars() -> int:
    return platform_int("telegram", "max_message_chars", default=4090)


def draft_max_chars() -> int:
    """sendMessageDraft text limit (Telegram Bot API)."""
    return platform_int("telegram", "draft_max_chars", default=4096)


def flood_retry_after_padding_sec() -> float:
    ms = platform_int("telegram", "flood_retry_after_padding_ms", default=250)
    return max(0.0, ms / 1000.0)


def flood_notify_seconds_default() -> int:
    return max(1, platform_int("telegram", "flood_notify_seconds_default", default=30))
