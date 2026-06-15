"""Persist daily check-in prompt/snooze/completion (survives bot restart)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from planning_bot.services.ritual_day import ritual_day_date
from shared.paths import vault_root_optional
from shared.tz import get_tz


def _state_path() -> Path | None:
    root = vault_root_optional()
    if root is None:
        return None
    return root / ".sync" / "daily_checkin_state.json"


def _load() -> dict[str, Any]:
    path = _state_path()
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, Any]) -> None:
    path = _state_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _active_ritual_day() -> str:
    return ritual_day_date()


def completed_for_today() -> bool:
    return _load().get("completed_date") == _active_ritual_day()


def mark_completed(day: str | None = None) -> None:
    data = _load()
    data["completed_date"] = (day or "").strip() or _active_ritual_day()
    data.pop("snooze_until", None)
    _save(data)


def mark_snooze(minutes: int) -> None:
    tz = get_tz()
    until = datetime.now(timezone.utc).astimezone(tz) + timedelta(minutes=minutes)
    data = _load()
    data["snooze_until"] = until.isoformat(timespec="seconds")
    data["last_prompt_date"] = _active_ritual_day()
    _save(data)


def _scheduled_prompt_due(ritual: str) -> bool:
    from planning_bot.services.daily_checkin_config import checkin_schedule

    try:
        day = datetime.fromisoformat(ritual).date()
    except ValueError:
        return True
    hour, minute = checkin_schedule()
    tz = get_tz()
    scheduled = datetime(
        day.year,
        day.month,
        day.day,
        max(0, min(23, int(hour))),
        max(0, min(59, int(minute))),
        tzinfo=tz,
    )
    now = datetime.now(timezone.utc).astimezone(tz)
    return now >= scheduled


def should_send_scheduled_prompt() -> bool:
    ritual = _active_ritual_day()
    data = _load()
    if data.get("completed_date") == ritual:
        if data.get("last_prompt_date") != ritual and not _scheduled_prompt_due(ritual):
            return True
        return False
    snooze = data.get("snooze_until")
    if not snooze:
        return True
    try:
        tz = get_tz()
        until = datetime.fromisoformat(str(snooze))
        if until.tzinfo is None:
            until = until.replace(tzinfo=tz)
        now = datetime.now(timezone.utc).astimezone(tz)
        return now >= until
    except (TypeError, ValueError):
        return True


def mark_prompt_sent() -> None:
    data = _load()
    data["last_prompt_date"] = _active_ritual_day()
    _save(data)
