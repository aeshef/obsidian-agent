"""LLM numeric params from finance_bot/config/llm_config.yaml."""
from __future__ import annotations

from bot.config_loader import get_llm_config


def llm_temperature(kind: str) -> float:
    cfg = get_llm_config()
    temps = cfg.get("temperature") if isinstance(cfg.get("temperature"), dict) else {}
    try:
        return float((temps or {}).get(kind, (temps or {}).get("text", 0.7)))
    except (TypeError, ValueError):
        return 0.7


def llm_timeout(kind: str) -> float:
    cfg = get_llm_config()
    timeouts = cfg.get("timeout") if isinstance(cfg.get("timeout"), dict) else {}
    try:
        return float((timeouts or {}).get(kind, (timeouts or {}).get("default", 60.0)))
    except (TypeError, ValueError):
        return 60.0


def llm_max_tokens(key: str) -> int | None:
    cfg = get_llm_config()
    mt = cfg.get("max_tokens") if isinstance(cfg.get("max_tokens"), dict) else {}
    raw = (mt or {}).get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
