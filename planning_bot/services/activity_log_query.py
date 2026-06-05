from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Dict, List, Optional, Set

from planning_bot.core.config import DONE_COLUMN
from planning_bot.core.pdmsg import pdmsg


def activity_events_limits() -> tuple[int, int]:
    from shared.agent.platform_config import platform_int

    default_lim = platform_int(
        "planning_action_log", "activity_events_limit_default", default=40
    )
    max_lim = platform_int(
        "planning_action_log", "activity_events_limit_max", default=1000
    )
    return max(1, default_lim), max(default_lim, max_lim)


def clamp_activity_limit(limit: int) -> int:
    """0 = no tail cap (full window up to safety_max); else clamp to [1, max]."""
    default_lim, max_lim = activity_events_limits()
    if limit == 0:
        return 0
    return max(1, min(int(limit or default_lim), max_lim))


def fetch_activity_events(
    logger,
    *,
    from_date: Optional[date],
    to_date: Optional[date],
    event_types: Optional[Set[str]],
    task_id: Optional[str],
    task_title: Optional[str],
    limit: int,
) -> tuple[List[Dict], List[Dict], int, Dict[str, int]]:
    """Return (display_entries, all_entries, n_raw, type_counts)."""
    all_entries, n_raw = logger.query_task_events(
        from_date=from_date,
        to_date=to_date,
        event_types=event_types,
        task_id=task_id,
        task_title=task_title,
        limit=0,
    )
    counts = dict(Counter(e.get("type") or "?" for e in all_entries))
    if limit > 0 and len(all_entries) > limit:
        display = all_entries[-limit:]
    else:
        display = all_entries
    return display, all_entries, n_raw, counts


def unique_completions(all_entries: List[Dict]) -> List[Dict]:
    """One row per closed task (task_completed or move to DONE), deduped by task_id."""
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    result: List[Dict] = []
    for e in all_entries:
        t = e.get("type")
        d = e.get("data") or {}
        if t == "task_completed":
            pass
        elif t == "task_moved" and d.get("to") == DONE_COLUMN:
            pass
        else:
            continue
        tid = (d.get("task_id") or "").strip()
        title = (d.get("title") or "").strip()
        if tid:
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
        elif title:
            if title in seen_titles:
                continue
            seen_titles.add(title)
        else:
            continue
        result.append(e)
    return result


def format_completion_hour_histogram(all_entries: List[Dict]) -> str:
    hours: Counter[int] = Counter()
    for e in all_entries:
        if e.get("type") != "task_completed":
            continue
        ts = str(e.get("timestamp", ""))
        if len(ts) < 13:
            continue
        try:
            hours[int(ts[11:13])] += 1
        except ValueError:
            continue
    if not hours:
        return ""
    lines = [
        pdmsg("agent_action_log_hour_header", n=sum(hours.values())),
        pdmsg("agent_action_log_hour_columns"),
    ]
    for h in range(24):
        c = hours.get(h, 0)
        if c:
            lines.append(pdmsg("agent_action_log_hour_row", hour=f"{h:02d}", count=c))
    return "\n".join(lines)


def format_activity_events_block(
    entries: List[Dict],
    all_entries: List[Dict],
    *,
    n_raw: int,
    type_counts: Dict[str, int],
    filtered_type: Optional[str],
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> str:
    lines: List[str] = []
    if period_start and period_end:
        lines.append(
            pdmsg(
                "agent_action_log_period",
                start=period_start.isoformat(),
                end=period_end.isoformat(),
            )
        )
    unique = unique_completions(all_entries)
    if unique:
        titles = "; ".join(
            ((e.get("data") or {}).get("title") or "?").replace("\n", " ") for e in unique
        )
        lines.append(
            pdmsg(
                "agent_action_log_unique_completions",
                count=len(unique),
                titles=titles,
            )
        )
        lines.append(pdmsg("agent_action_log_completion_note"))

    if filtered_type:
        lines.append(
            pdmsg(
                "agent_action_log_summary_filtered",
                shown=len(entries),
                total=n_raw,
                event_type=filtered_type,
            )
        )
        hist = format_completion_hour_histogram(all_entries)
        if hist:
            lines.append(hist)
    else:
        lines.append(
            pdmsg(
                "agent_action_log_summary",
                shown=len(entries),
                total=n_raw,
                completed=type_counts.get("task_completed", 0),
                moved=type_counts.get("task_moved", 0),
                created=type_counts.get("task_created", 0),
                unique_completed=len(unique),
            )
        )
    if len(entries) < n_raw:
        lines.append(
            pdmsg(
                "agent_action_log_tail_truncated",
                shown=len(entries),
                total=n_raw,
            )
        )
    for e in entries:
        ts = e.get("timestamp") or "?"
        t = e.get("type") or "?"
        d = e.get("data") or {}
        title = (d.get("title") or "?").replace("\n", " ")
        if t == "task_moved":
            lines.append(f"{ts} | {t} | \"{title}\" | {d.get('from', '')} → {d.get('to', '')}")
        elif t == "task_completed":
            lines.append(f"{ts} | {t} | \"{title}\"")
        elif t == "task_created":
            lines.append(
                f"{ts} | {t} | \"{title}\" | {d.get('category', '')} / {d.get('priority', '')}"
            )
        else:
            lines.append(f"{ts} | {t} | \"{title}\"")
    return "\n".join(lines)
