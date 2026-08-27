"""Resolve agent context/dump caps from platform.yaml (no magic literals in call sites).

Spec-driven rules:
- single calendar day activity dumps default to full window (limit=0)
- tool_result / verify excerpts can be floored from calibrate stats (quantile file)
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from shared.agent.platform_config import platform_float, platform_int, platform_value


def activity_events_default_limit() -> int:
    return max(1, platform_int("planning_action_log", "activity_events_limit_default", default=200))


def activity_events_max_limit() -> int:
    default = activity_events_default_limit()
    return max(default, platform_int("planning_action_log", "activity_events_limit_max", default=2000))


def activity_events_single_day_limit() -> int:
    """0 = full day window (up to safety_max)."""
    return max(0, platform_int("planning_action_log", "activity_events_single_day_limit", default=0))


def clamp_activity_limit(limit: int) -> int:
    """0 = no tail cap; else clamp to [1, max]."""
    max_lim = activity_events_max_limit()
    if limit == 0:
        return 0
    default_lim = activity_events_default_limit()
    return max(1, min(int(limit or default_lim), max_lim))


def resolve_activity_limit(
    *,
    requested: int,
    from_date: Optional[date],
    to_date: Optional[date],
) -> int:
    """Pick dump limit for get_activity_events.

    ``requested < 0`` → auto: one calendar day uses ``single_day_limit`` (default 0),
    otherwise ``activity_events_limit_default``.
    ``requested == 0`` → full window.
    ``requested > 0`` → clamped explicit tail.
    """
    req = int(requested)
    if req > 0:
        return clamp_activity_limit(req)
    if req == 0:
        return 0
    if from_date is not None and to_date is not None and from_date == to_date:
        return clamp_activity_limit(activity_events_single_day_limit())
    return clamp_activity_limit(activity_events_default_limit())


def tool_result_max_chars() -> int:
    base = platform_int("agent", "tool_result_max_chars", default=16000)
    return _apply_stats_floor("tool_result_chars", base)


def verify_excerpt_max_chars() -> int:
    from shared.agent.config import load_models_config

    raw = (load_models_config().get("verify") or {}).get("tools_excerpt_max_chars")
    try:
        base = int(raw) if raw is not None else 12000
    except (TypeError, ValueError):
        base = 12000
    return _apply_stats_floor("verify_excerpt_chars", max(0, base))


def _apply_stats_floor(key: str, configured: int) -> int:
    """If calibrate wrote budget_stats.json, never go below recommended floor."""
    stats = _load_budget_stats()
    rec = stats.get("recommended") or {}
    try:
        floor = int(rec.get(key) or 0)
    except (TypeError, ValueError):
        floor = 0
    if floor <= 0:
        return max(0, configured)
    return max(configured, floor)


@lru_cache(maxsize=1)
def _load_budget_stats() -> dict[str, Any]:
    path = _budget_stats_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _budget_stats_path() -> Path:
    raw = str(platform_value("agent_budgets", "stats_path", default="") or "").strip()
    if raw:
        return Path(raw).expanduser()
    from shared.agent.config import agent_config_dir

    return agent_config_dir() / "budget_stats.json"


def quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    q = min(1.0, max(0.0, float(q)))
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return float(sorted_vals[lo]) * (1 - frac) + float(sorted_vals[hi]) * frac


def recommend_cap(
    samples: list[int],
    *,
    q: float | None = None,
    headroom: float | None = None,
    floor: int | None = None,
    ceiling: int | None = None,
) -> int:
    """p_q(samples) * headroom, clamped to [floor, ceiling]."""
    if q is None:
        q = platform_float("agent_budgets", "quantile", default=0.95)
    if headroom is None:
        headroom = platform_float("agent_budgets", "headroom", default=1.2)
    if floor is None:
        floor = platform_int("agent_budgets", "floor_chars", default=8000)
    if ceiling is None:
        ceiling = platform_int("agent_budgets", "ceiling_chars", default=48000)
    if not samples:
        return max(floor, 0)
    vals = sorted(float(x) for x in samples if x is not None and int(x) >= 0)
    if not vals:
        return max(floor, 0)
    raw = quantile(vals, q) * float(headroom)
    return int(max(floor, min(ceiling, round(raw))))


def clear_budget_caches() -> None:
    _load_budget_stats.cache_clear()
