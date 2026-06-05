"""Planning LLM temps/timeouts from config/agent/platform.yaml planning_llm section."""
from __future__ import annotations

from shared.agent.platform_config import platform_float


def planning_llm_temperature(key: str, default: float) -> float:
    return platform_float("planning_llm", key, default=default)


def planning_chat_timeout_sec() -> float:
    return platform_float("planning_llm", "chat_timeout_sec", default=90.0)
