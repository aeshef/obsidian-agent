"""Read Calendar.json and build LLM context blocks."""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from planning_bot.core.pdmsg import pdmsg
from shared.tz import now_in_tz, today_in_tz

logger = logging.getLogger(__name__)

_CALENDAR_TZ = os.environ.get("CALENDAR_TZ") or os.environ.get("TIMEZONE")


def _today_in_calendar_tz() -> date:
    """Return today's date in CALENDAR_TZ / TIMEZONE."""
    return today_in_tz(_CALENDAR_TZ)


def _now_in_calendar_tz() -> datetime:
    return now_in_tz(_CALENDAR_TZ)


def with_calendar_attendance_note(body: str) -> str:
    """Append remote-work / soft-meeting context. Empty body is unchanged."""
    b = (body or "").strip()
    if not b:
        return ""
    return pdmsg("calendar_attendance_context") + "\n\n" + b


def format_calendar_prompt_status(cal_raw: Optional[str]) -> str:
    """
    Short Telegram status: whether calendar context reached the review prompt.
    Shows the first lines of the same summary sent to the LLM.
    """
    raw = (cal_raw or "").strip()
    if not raw:
        return pdmsg("calendar_prompt_status_empty")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()][:3]
    body = "\n".join(lines)
    return pdmsg("calendar_prompt_status_ok", preview=body)


def _load_bundle(json_path: Path) -> dict:
    if not json_path.exists():
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to read calendar JSON file: %s", e)
        return {}


def _load(json_path: Path) -> List[Dict]:
    return list(_load_bundle(json_path).get("events") or [])


def _in_range(event: Dict, start: date, end: date) -> bool:
    try:
        ev_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        return start <= ev_date <= end
    except (ValueError, KeyError):
        return False


def _event_sort_key(ev: Dict):
    """Chronological sort key (date, start time)."""
    try:
        d = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        t = ev.get("start") or "00:00"
        return (d, t)
    except (ValueError, KeyError, TypeError):
        return (date.min, "00:00")


def _format_event(ev: Dict) -> str:
    tag = ev.get("tag")
    title = ev.get("title") or ""
    if tag:
        prefix = f"[{tag}]"
        if title.startswith(prefix):
            title = title[len(prefix) :].strip()
    tag_s = f"[{tag}] " if tag else ""
    cancelled = pdmsg("calendar_event_cancelled_prefix") if ev.get("is_cancelled") else ""
    if ev.get("is_allday"):
        return pdmsg(
            "calendar_event_allday",
            date=ev["date"],
            cancelled=cancelled,
            tag=tag_s,
            title=title,
        )
    return pdmsg(
        "calendar_event_timed",
        date=ev["date"],
        start=ev["start"],
        end=ev["end"],
        cancelled=cancelled,
        tag=tag_s,
        title=title,
    )


def get_upcoming_events_text(json_path: Path, hours_ahead: int = 48) -> str:
    """
    Text for upcoming events (today plus the next N hours).
    Used as context when creating a task.
    """
    events = _load(json_path)
    if not events:
        return ""

    now = _now_in_calendar_tz()
    today = now.date()
    until = (now + timedelta(hours=hours_ahead)).date()

    upcoming = [
        e for e in events
        if not e.get("is_cancelled")
        and _in_range(e, today, until)
    ]
    if not upcoming:
        return ""

    lines = [pdmsg("calendar_upcoming_header")]
    for ev in upcoming:
        lines.append(_format_event(ev))

    return "\n".join(lines)


def get_week_calendar_summary(json_path: Path, days_back: int = 7, days_ahead: int = 7) -> str:
    """
    Brief event summary for a date window.
    Used in reflection and recommendations.
    Returns timed meeting counts/hours plus all-day events as a separate block.
    """
    events = _load(json_path)
    if not events:
        return ""

    today = _today_in_calendar_tz()
    start = today - timedelta(days=days_back)
    end = today + timedelta(days=days_ahead)

    window = [e for e in events if _in_range(e, start, end)]
    timed_in_window = [e for e in window if not e.get("is_allday")]
    allday_in_window = [e for e in window if e.get("is_allday")]

    timed_in_window.sort(key=_event_sort_key)
    cancelled_timed = [e for e in timed_in_window if e.get("is_cancelled")]
    active_timed = [e for e in timed_in_window if not e.get("is_cancelled")]

    allday_active = [e for e in allday_in_window if not e.get("is_cancelled")]
    allday_cancelled = [e for e in allday_in_window if e.get("is_cancelled")]
    allday_active.sort(key=_event_sort_key)

    total_minutes = 0
    for ev in active_timed:
        try:
            t0 = datetime.strptime(ev["start"], "%H:%M")
            t1 = datetime.strptime(ev["end"], "%H:%M")
            diff = (t1 - t0).seconds // 60
            if 0 < diff <= 480:
                total_minutes += diff
        except ValueError:
            pass

    hours = total_minutes // 60
    mins = total_minutes % 60

    cancelled_note = (
        pdmsg("calendar_week_cancelled_note", n=len(cancelled_timed))
        if cancelled_timed
        else ""
    )
    lines = [
        pdmsg(
            "calendar_week_header",
            start=start.strftime("%d.%m"),
            end=end.strftime("%d.%m"),
        ),
        pdmsg(
            "calendar_week_timed_stats",
            count=len(active_timed),
            hours=hours,
            mins=mins,
            cancelled_note=cancelled_note,
        ),
    ]

    if allday_active or allday_cancelled:
        allday_cancelled_note = (
            pdmsg("calendar_week_allday_cancelled_note", n=len(allday_cancelled))
            if allday_cancelled
            else ""
        )
        lines.append(
            pdmsg(
                "calendar_week_allday_stats",
                active=len(allday_active),
                cancelled_note=allday_cancelled_note,
            )
        )
        max_allday = 28
        pool = allday_active + [e for e in allday_cancelled]
        pool.sort(key=_event_sort_key)
        shown = pool[:max_allday]
        if len(pool) > max_allday:
            lines.append(
                pdmsg(
                    "calendar_week_allday_truncated",
                    max=max_allday,
                    total=len(pool),
                )
            )
        for ev in shown:
            lines.append(_format_event(ev))

    past = [
        e for e in active_timed
        if datetime.strptime(e["date"], "%Y-%m-%d").date() <= today
    ]
    future = [
        e for e in active_timed
        if datetime.strptime(e["date"], "%Y-%m-%d").date() > today
    ]

    max_past, max_future = 25, 18
    if past:
        lines.append(pdmsg("calendar_week_past_header", count=len(past)))
        tail = past[-max_past:] if len(past) > max_past else past
        if len(past) > max_past:
            lines.append(
                pdmsg(
                    "calendar_week_past_truncated",
                    max=max_past,
                    total=len(past),
                )
            )
        for ev in tail:
            lines.append(_format_event(ev))

    if future:
        lines.append(pdmsg("calendar_week_future_header", count=len(future)))
        head = future[:max_future]
        if len(future) > max_future:
            lines.append(
                pdmsg(
                    "calendar_week_future_truncated",
                    max=max_future,
                    total=len(future),
                )
            )
        for ev in head:
            lines.append(_format_event(ev))

    return "\n".join(lines)


def get_events_for_day_text(json_path: Path, day: date) -> str:
    """Events for a single calendar day."""
    return get_events_in_range_text(json_path, day, day)


def _calendar_range_max_events() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int("planning_calendar", "range_max_events", default=400)


def get_events_in_range_text(
    json_path: Path,
    start: date,
    end: date,
    *,
    max_events: int | None = None,
) -> str:
    """Timed and all-day events in [start, end], chronological."""
    bundle = _load_bundle(json_path)
    events = list(bundle.get("events") or [])
    cap = max_events if max_events is not None else _calendar_range_max_events()
    window = [e for e in events if _in_range(e, start, end)]
    single_day = start == end
    if not window:
        from planning_bot.services.calendar_retention import (
            detail_cutoff,
            format_archive_range_summary,
        )

        archive_note = format_archive_range_summary(bundle.get("archive"), start, end)
        if archive_note and start < detail_cutoff():
            return archive_note
        if single_day:
            return pdmsg("calendar_day_empty", day=start.isoformat())
        return pdmsg(
            "calendar_range_empty",
            start=start.isoformat(),
            end=end.isoformat(),
        )
    window.sort(key=_event_sort_key)
    total = len(window)
    truncated = False
    if cap > 0 and total > cap:
        window = window[:cap]
        truncated = True
    if single_day:
        lines = [pdmsg("calendar_day_header", day=start.isoformat())]
    else:
        lines = [
            pdmsg(
                "calendar_range_header",
                start=start.isoformat(),
                end=end.isoformat(),
                shown=len(window),
                total=total,
            )
        ]
    if truncated:
        lines.append(
            pdmsg("calendar_range_truncated", max=cap, total=total)
        )
    for ev in window:
        lines.append(_format_event(ev))
    return with_calendar_attendance_note("\n".join(lines))


def _calendar_meta_footer(json_path: Path) -> str:
    """Freshness line for Calendar.json so the agent can warn on stale data."""
    if not json_path.exists():
        return pdmsg("calendar_meta_missing")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            meta = (json.load(f).get("meta") or {})
    except Exception as e:
        return pdmsg("calendar_meta_read_error", error=e)
    updated = meta.get("last_updated") or meta.get("txt_last_parsed") or "?"
    total = meta.get("total_events")
    tail = f"meta: last_updated={updated}"
    if total is not None:
        tail += f", events={total}"
    try:
        from planning_bot.core.config import CALENDAR_TXT_FILE

        if CALENDAR_TXT_FILE.exists():
            from planning_bot.tools.calendar_sync import _extract_txt_timestamp

            txt_ts = _extract_txt_timestamp(CALENDAR_TXT_FILE.read_text(encoding="utf-8"))
            parsed = meta.get("txt_last_parsed")
            if txt_ts and parsed and txt_ts != parsed:
                tail += pdmsg(
                    "calendar_meta_txt_newer",
                    txt_ts=txt_ts,
                    json_ts=parsed,
                )
    except Exception:
        pass
    return tail


def _calendar_tool_max_chars() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int("planning_calendar", "tool_max_chars", default=4000)


def _calendar_chat_upcoming_hours() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int("planning_calendar", "chat_upcoming_hours", default=72)


def get_calendar_for_tool(
    json_path: Path,
    *,
    day: str = "",
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    hours_ahead: int | None = None,
    max_chars: int | None = None,
) -> str:
    """
    day → one calendar day; from_date/to_date/days → event list in range;
    otherwise upcoming hours_ahead + week summary.
    """
    from shared.query.agent_interval import IntervalMode, resolve_agent_interval

    if hours_ahead is None:
        from shared.agent.platform_config import platform_int

        hours_ahead = platform_int("planning_calendar", "default_hours_ahead", default=48)
    cap = max_chars if max_chars is not None else _calendar_tool_max_chars()

    meta_line = _calendar_meta_footer(json_path)
    prefix = pdmsg("calendar_tool_prefix")
    interval = resolve_agent_interval(
        point_day=day,
        from_date=from_date,
        to_date=to_date,
        days=days,
    )

    if interval.mode == IntervalMode.POINT_DAY and interval.point_day:
        body = get_events_for_day_text(json_path, interval.point_day)
    elif interval.mode == IntervalMode.DATE_RANGE and interval.date_range:
        dr = interval.date_range
        if not dr.start or not dr.end:
            return pdmsg("calendar_tool_empty", meta=meta_line)
        body = get_events_in_range_text(json_path, dr.start, dr.end)
    else:
        body = get_chat_calendar_context(json_path, max_chars=cap)
        if not body:
            return pdmsg("calendar_tool_empty", meta=meta_line)
        return body + f"\n\n[{meta_line}]"

    if not (body or "").strip():
        return pdmsg("calendar_tool_empty", meta=meta_line)
    if len(body) > cap:
        body = body[: cap - 20].rstrip() + pdmsg("calendar_truncated_suffix")
    return prefix + "\n" + body + f"\n\n[{meta_line}]"


def get_chat_calendar_context(json_path: Path, max_chars: int | None = None) -> str:
    """
    Compact LLM block: upcoming hours plus week summary (limits from platform.yaml).
    """
    cap = max_chars if max_chars is not None else _calendar_tool_max_chars()
    from shared.agent.platform_config import platform_int

    upcoming_h = platform_int("planning_calendar", "chat_upcoming_hours", default=72)
    week_ahead = platform_int("planning_calendar", "week_summary_days_ahead", default=7)
    parts: List[str] = []
    upcoming = get_upcoming_events_text(json_path, hours_ahead=upcoming_h)
    if upcoming:
        parts.append(upcoming)
    week = get_week_calendar_summary(json_path, days_back=0, days_ahead=week_ahead)
    if week:
        parts.append(week)
    if not parts:
        return ""
    s = "\n\n".join(parts)
    if len(s) > cap:
        s = s[: cap - 20].rstrip() + pdmsg("calendar_truncated_suffix")
    s = with_calendar_attendance_note(s)
    return pdmsg("calendar_chat_header") + s
