"""Config-driven policy for scheduled Telegram pushes (less spam, coherent times).

All times/flags come from ``push_policy`` in platform.yaml — not scenario code.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.agent.platform_config import platform_bool, platform_int, platform_section


def _block() -> dict[str, Any]:
    return platform_section("push_policy")


def _as_bool(raw: Any, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(int(raw))
    s = str(raw or "").strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return default


def _nested(path: str) -> dict[str, Any]:
    cur: Any = _block()
    for part in path.split("."):
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(part) or {}
    return cur if isinstance(cur, dict) else {}


def _nested_int(path: str, key: str, default: int) -> int:
    block = _nested(path)
    if key in block and block.get(key) is not None:
        try:
            return int(block[key])
        except (TypeError, ValueError):
            pass
    return default


def _nested_bool(path: str, key: str, default: bool) -> bool:
    block = _nested(path)
    if key in block:
        return _as_bool(block.get(key), default)
    return default


def _nested_str(path: str, key: str, default: str) -> str:
    block = _nested(path)
    if key in block and block.get(key) is not None:
        return str(block.get(key)).strip()
    return default


# ── quiet hours ─────────────────────────────────────────────────────────────


def quiet_hours_start() -> int:
    return _nested_int("quiet_hours", "start", 23)


def quiet_hours_end() -> int:
    return _nested_int("quiet_hours", "end", 7)


def in_quiet_hours(now: datetime | None = None) -> bool:
    """True inside [start, end) wrapping midnight. Disabled when start==end."""
    start = quiet_hours_start() % 24
    end = quiet_hours_end() % 24
    if start == end:
        return False
    if now is None:
        now = datetime.now()
    h = now.hour
    if start < end:
        return start <= h < end
    return h >= start or h < end


# ── morning brief / planning ────────────────────────────────────────────────


def morning_brief_enabled() -> bool:
    nested = _block().get("morning_brief") or {}
    if isinstance(nested, dict) and "enabled" in nested:
        return _as_bool(nested.get("enabled"), True)
    return platform_bool("push_policy", "morning_brief_enabled", default=True)


def morning_brief_hour() -> int:
    return _nested_int("morning_brief", "hour", 8)


def morning_brief_minute() -> int:
    return _nested_int("morning_brief", "minute", 15)


def morning_brief_includes(key: str, *, default: bool = True) -> bool:
    nested = _block().get("morning_brief") or {}
    if not isinstance(nested, dict):
        return default
    include = nested.get("include") or {}
    if not isinstance(include, dict) or key not in include:
        return default
    return _as_bool(include.get(key), default)


def separate_morning_routine_hours() -> list[int]:
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


def evening_routine_hours() -> list[int]:
    nested = _block().get("routines_evening_hours")
    if nested is None:
        # Default quiet: daily check-in replaces the old 21/22/23 triple spam.
        return []
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
    if morning_brief_enabled() and morning_brief_includes("stuck", default=True):
        return False
    return _nested_bool("stuck_alerts", "enabled", True)


def separate_deadlines_alerts_enabled() -> bool:
    if morning_brief_enabled() and morning_brief_includes("deadlines", default=True):
        return False
    return True


def separate_goals_alerts_enabled() -> bool:
    if morning_brief_enabled() and morning_brief_includes("goals", default=True):
        return False
    return True


# ── finance pushes ──────────────────────────────────────────────────────────


def finance_txn_reminder_enabled() -> bool:
    return _nested_bool("finance_txn_reminder", "enabled", True)


def finance_txn_reminder_hour() -> int:
    return _nested_int("finance_txn_reminder", "hour", 21)


def finance_txn_reminder_minute() -> int:
    return _nested_int("finance_txn_reminder", "minute", 0)


def finance_txn_reminder_only_if_no_txn() -> bool:
    return _nested_bool("finance_txn_reminder", "only_if_no_txn_today", True)


def finance_subscriptions_enabled() -> bool:
    return _nested_bool("finance_subscriptions", "enabled", True)


def finance_subscriptions_hour() -> int:
    return _nested_int("finance_subscriptions", "hour", 10)


def finance_subscriptions_minute() -> int:
    return _nested_int("finance_subscriptions", "minute", 0)


def finance_daily_insight_enabled() -> bool:
    # Default off — was a major feed-spam source (MWF + jitter).
    return _nested_bool("finance_daily_insight", "enabled", False)


def finance_daily_insight_days() -> str:
    return _nested_str("finance_daily_insight", "days", "mon,wed,fri") or "mon,wed,fri"


def finance_daily_insight_hour() -> int:
    return _nested_int("finance_daily_insight", "hour", 9)


def finance_daily_insight_minute() -> int:
    return _nested_int("finance_daily_insight", "minute", 0)


def finance_daily_insight_jitter_sec() -> int:
    return _nested_int("finance_daily_insight", "jitter_sec", 7200)


def finance_weekly_analysis_enabled() -> bool:
    return _nested_bool("finance_weekly_analysis", "enabled", True)


def finance_weekly_analysis_dow() -> str:
    return _nested_str("finance_weekly_analysis", "day_of_week", "sun") or "sun"


def finance_weekly_analysis_hour() -> int:
    return _nested_int("finance_weekly_analysis", "hour", 19)


def finance_weekly_analysis_minute() -> int:
    return _nested_int("finance_weekly_analysis", "minute", 0)


def finance_monthly_analysis_enabled() -> bool:
    return _nested_bool("finance_monthly_analysis", "enabled", True)


def finance_monthly_analysis_day() -> int:
    return _nested_int("finance_monthly_analysis", "day", 1)


def finance_monthly_analysis_hour() -> int:
    return _nested_int("finance_monthly_analysis", "hour", 9)


def finance_monthly_analysis_minute() -> int:
    return _nested_int("finance_monthly_analysis", "minute", 0)


# ── knowledge serendipity ───────────────────────────────────────────────────


def serendipity_push_enabled() -> bool:
    """Optional gate on top of SERENDIPITY_ENABLED / capabilities connector."""
    return _nested_bool("serendipity", "enabled", True)


def serendipity_hour_start() -> int:
    return _nested_int("serendipity", "hour_start", 11)


def serendipity_hour_end() -> int:
    return _nested_int("serendipity", "hour_end", 20)


# ── host UI (buttons) ───────────────────────────────────────────────────────


def host_ui_block() -> dict[str, Any]:
    block = platform_section("host_ui")
    return block if isinstance(block, dict) else {}


def show_auto_mode_button() -> bool:
    """Separate Assistant/chat mode button — redundant when free text is unified."""
    block = host_ui_block()
    if "show_auto_mode_button" in block:
        return _as_bool(block.get("show_auto_mode_button"), False)
    return False


def show_knowledge_query_button() -> bool:
    """KB query tip button — free text already hits unified agent."""
    block = host_ui_block()
    if "show_knowledge_query_button" in block:
        return _as_bool(block.get("show_knowledge_query_button"), False)
    return False
