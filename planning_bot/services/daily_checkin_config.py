"""Daily check-in schema from planning_bot/config/daily_checkin.yaml (+ platform.yaml overrides)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from planning_bot.core.settings import get_config_path
from shared.agent.platform_config import platform_int, platform_value
from shared.yaml_config import load_merged_config


@lru_cache(maxsize=1)
def load_daily_checkin_config() -> dict[str, Any]:
    return load_merged_config(str(get_config_path()), "daily_checkin")


def _checkin_block() -> dict[str, Any]:
    block = load_daily_checkin_config().get("checkin")
    return dict(block) if isinstance(block, dict) else {}


def checkin_schedule() -> tuple[int, int]:
    block = _checkin_block()
    sched = block.get("schedule") if isinstance(block.get("schedule"), dict) else {}
    hour = platform_int(
        "planning_checkin",
        "hour",
        default=int(sched.get("hour", 23)) if sched.get("hour") is not None else 23,
    )
    minute = platform_int(
        "planning_checkin",
        "minute",
        default=int(sched.get("minute", 45)) if sched.get("minute") is not None else 45,
    )
    return hour, minute


def checkin_snooze_minutes() -> int:
    block = _checkin_block()
    default = int(block.get("snooze_minutes", 30))
    return platform_int("planning_checkin", "snooze_minutes", default=default)


def routine_sections_order() -> list[str]:
    block = _checkin_block()
    raw = block.get("routine_sections")
    if isinstance(raw, list) and raw:
        return [str(x).strip() for x in raw if str(x).strip()]
    return ["evening", "day"]


def replace_passive_evening_reminders() -> bool:
    block = _checkin_block()
    default = bool(block.get("replace_passive_evening_reminders", True))
    raw = platform_value("planning_checkin", "replace_passive_evening_reminders", default=default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def skip_already_checked_routines() -> bool:
    block = _checkin_block()
    return bool(block.get("skip_already_checked_routines", True))


def scales_config() -> dict[str, Any]:
    raw = load_daily_checkin_config().get("scales")
    return dict(raw) if isinstance(raw, dict) else {}


def signals_config() -> list[dict[str, Any]]:
    raw = load_daily_checkin_config().get("signals")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("id"):
            out.append(dict(item))
    return out
