from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
import os
from datetime import date, datetime

from shared.tz import now_in_tz, today_in_tz

_TZ = os.environ.get("CALENDAR_TZ") or os.environ.get("TIMEZONE")


def reference_now() -> datetime:
    return now_in_tz(_TZ)


def reference_today() -> date:
    return today_in_tz(_TZ)


def reference_today_iso() -> str:
    return reference_today().isoformat()


def format_reference_today_label() -> str:
    """Locale weekday + ISO date for agent prompts (TIMEZONE anchor)."""
    today = reference_today()
    weekday = today.strftime("%A")
    try:
        from planning_bot.core.llm_context import lctx

        names = [n.strip() for n in lctx("weekday_names").strip().split("|") if n.strip()]
        if len(names) > today.weekday():
            weekday = names[today.weekday()]
    except Exception:
        pass
    return f"{today.isoformat()} ({weekday})"


def resolve_calendar_day_from_text(text: str, *, today: date | None = None) -> date | None:
    'Operation implementation.'
    from shared.parsing.relative_calendar import resolve_calendar_day_from_text as _resolve

    return _resolve(text, today=today or reference_today())


def format_deadline_hint(deadline: str | None, today: str | None = None) -> str:
    'Operation implementation.'
    if not deadline:
        return ""
    ref = today or reference_today_iso()
    if deadline < ref:
        return pdmsg("auto_84fd036a89", deadline={deadline})
    if deadline == ref:
        return pdmsg("auto_0672d5ba92", deadline={deadline})
    return pdmsg("auto_90857e8a76", deadline={deadline})
