"""Resolve LLM numeric defaults from config/agent/models.yaml (no hardcoded temps in callers)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _models_block() -> dict[str, Any]:
    from shared.agent.config import load_models_config

    return load_models_config()


def _role_block(role: str) -> dict[str, Any]:
    roles = _models_block().get("roles") or {}
    block = roles.get(role) or roles.get("analyze") or {}
    return block if isinstance(block, dict) else {}


def _global_defaults() -> dict[str, Any]:
    raw = _models_block().get("defaults") or {}
    return raw if isinstance(raw, dict) else {}


def role_temperature(role: str, *, override: float | None = None) -> float:
    if override is not None:
        return override
    block = _role_block(role)
    try:
        return float(block.get("temperature", _global_defaults().get("temperature", 0.2)))
    except (TypeError, ValueError):
        return 0.2


def role_timeout_sec(role: str, *, override: float | None = None) -> float:
    if override is not None:
        return override
    block = _role_block(role)
    try:
        return float(
            block.get("timeout_sec", _global_defaults().get("timeout_sec", 120.0))
        )
    except (TypeError, ValueError):
        return 120.0


def role_tool_choice(role: str, *, override: str | None = None) -> str:
    if override is not None:
        return override
    block = _role_block(role)
    raw = block.get("tool_choice", _global_defaults().get("tool_choice", "auto"))
    return str(raw) if raw else "auto"
