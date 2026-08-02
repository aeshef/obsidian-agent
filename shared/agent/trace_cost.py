"""Estimate LLM $ cost from agent traces (prices in platform.yaml, not code)."""
from __future__ import annotations

from typing import Any


# Conservative OpenAI-era defaults when platform.yaml has no pricing block.
_DEFAULT_PROMPT_PER_M = 0.14
_DEFAULT_COMPLETION_PER_M = 0.28


def _pricing_block() -> dict[str, Any]:
    try:
        from shared.agent.platform_config import platform_section

        block = platform_section("agent_trace").get("pricing") or {}
        return block if isinstance(block, dict) else {}
    except Exception:
        return {}


def pricing_for_model(model: str = "") -> tuple[float, float]:
    """Return (prompt_usd_per_1M, completion_usd_per_1M)."""
    cfg = _pricing_block()
    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    key = (model or "").strip() or str(cfg.get("default_model") or "").strip()
    row = models.get(key) if key else None
    if not isinstance(row, dict):
        # prefix match (deepseek-v4-flash-...)
        for name, cand in models.items():
            if key and str(name) in key and isinstance(cand, dict):
                row = cand
                break
    if not isinstance(row, dict):
        row = {}
    try:
        prompt = float(row.get("prompt_per_m") or cfg.get("prompt_per_m") or _DEFAULT_PROMPT_PER_M)
    except (TypeError, ValueError):
        prompt = _DEFAULT_PROMPT_PER_M
    try:
        completion = float(
            row.get("completion_per_m") or cfg.get("completion_per_m") or _DEFAULT_COMPLETION_PER_M
        )
    except (TypeError, ValueError):
        completion = _DEFAULT_COMPLETION_PER_M
    return prompt, completion


def estimate_cost_usd(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "",
) -> float:
    p_rate, c_rate = pricing_for_model(model)
    return (max(0, prompt_tokens) / 1_000_000.0) * p_rate + (
        max(0, completion_tokens) / 1_000_000.0
    ) * c_rate


def estimate_tokens_from_chars(chars: int) -> int:
    """Rough chars→tokens when provider usage is missing (≈4 chars/token)."""
    return max(0, int(chars) // 4)


def primary_model(llm_rounds: list[dict[str, Any]] | None) -> str:
    for r in llm_rounds or []:
        m = str((r or {}).get("model") or "").strip()
        if m:
            return m
    return ""
