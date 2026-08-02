"""Config-driven policy for scheduled Telegram pushes (less spam, coherent times)."""
from __future__ import annotations

from typing import Any

from shared.agent.platform_config import platform_bool, platform_int, platform_section


def _block() -> dict[str, Any]:
    return platform_section("push_policy")


def morning_brief_enabled() -> bool:
    nested = _block().get("morning_brief") or {}
    if isinstance(nested, dict) and "enabled" in nested:
        raw = nested.get("enabled")
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return platform_bool("push_policy", "morning_brief_enabled", default=True)


def morning_brief_hour() -> int:
    nested = _block().get("morning_brief") or {}
    if isinstance(nested, dict) and nested.get("hour") is not None:
        try:
            return int(nested["hour"])
        except (TypeError, ValueError):
            pass
    return platform_int("push_policy", "morning_brief_hour", default=8)


def morning_brief_minute() -> int:
    nested = _block().get("morning_brief") or {}
    if isinstance(nested, dict) and nested.get("minute") is not None:
        try:
            return int(nested["minute"])
        except (TypeError, ValueError):
            pass
    return platform_int("push_policy", "morning_brief_minute", default=15)


def morning_brief_includes(key: str, *, default: bool = True) -> bool:
    nested = _block().get("morning_brief") or {}
    if not isinstance(nested, dict):
        return default
    include = nested.get("include") or {}
    if not isinstance(include, dict) or key not in include:
        return default
    raw = include.get(key)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def separate_morning_routine_hours() -> list[int]:
    """When morning brief is on, default empty (no 8/9/10 spam). Else legacy hours."""
    nested = _block().get("routines_morning_hours")
    if nested is None:
        return [] if morning_brief_enabled() else [8, 9, 10]
    if not isinstance(nested, list):
        return []
    out: list[int] = []
    for h in nested:
        try:
            out.append(int(h))
        except (TypeError, ValueError):
            continue
    return out


def separate_stuck_alerts_enabled() -> bool:
    """Stuck tasks fold into morning brief when brief is enabled."""
    if morning_brief_enabled() and morning_brief_includes("stuck", default=True):
        return False
    nested = _block().get("stuck_alerts") or {}
    if isinstance(nested, dict) and "enabled" in nested:
        raw = nested.get("enabled")
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return True


def separate_deadlines_alerts_enabled() -> bool:
    if morning_brief_enabled() and morning_brief_includes("deadlines", default=True):
        return False
    return True


def separate_goals_alerts_enabled() -> bool:
    if morning_brief_enabled() and morning_brief_includes("goals", default=True):
        return False
    return True


def finance_txn_reminder_hour() -> int:
    nested = _block().get("finance_txn_reminder") or {}
    if isinstance(nested, dict) and nested.get("hour") is not None:
        try:
            return int(nested["hour"])
        except (TypeError, ValueError):
            pass
    return 21


def finance_txn_reminder_minute() -> int:
    nested = _block().get("finance_txn_reminder") or {}
    if isinstance(nested, dict) and nested.get("minute") is not None:
        try:
            return int(nested["minute"])
        except (TypeError, ValueError):
            pass
    return 0


def finance_txn_reminder_only_if_no_txn() -> bool:
    nested = _block().get("finance_txn_reminder") or {}
    if isinstance(nested, dict) and "only_if_no_txn_today" in nested:
        raw = nested.get("only_if_no_txn_today")
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return True


def finance_txn_reminder_enabled() -> bool:
    nested = _block().get("finance_txn_reminder") or {}
    if isinstance(nested, dict) and "enabled" in nested:
        raw = nested.get("enabled")
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return True
