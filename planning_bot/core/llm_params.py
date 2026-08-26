"""Planning LLM temps/timeouts from config/agent/platform.yaml planning_llm section."""
from __future__ import annotations

from shared.agent.platform_config import platform_float


def planning_llm_temperature(key: str) -> float:
    """Require a key under platform.yaml ``planning_llm`` (no call-site numeric fallbacks)."""
    return platform_float("planning_llm", key)


def planning_chat_timeout_sec() -> float:
    return platform_float("planning_llm", "chat_timeout_sec", default=90.0)
