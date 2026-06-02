"""Telegram API limits — from config/agent/platform.yaml."""
from __future__ import annotations

from shared.agent.platform_config import platform_int


def max_message_chars() -> int:
    return platform_int("telegram", "max_message_chars", default=4090)
