"""Planning agent tools for shared agent core."""
from __future__ import annotations

from planning_bot.core.config import DEFAULT_CATEGORY, DEFAULT_PRIORITY
from planning_bot.core.pdmsg import pdmsg

import logging
from typing import TYPE_CHECKING, List, Optional

from shared.agent.app import DomainAdapter
from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext, ModelRole
from shared.memory import InsightsMemory, ProfileMemory

if TYPE_CHECKING:
    from planning_bot.app.bot import PlanningBot

log = logging.getLogger("planning.agent_tools")

PLANNING_DOMAIN = "planning"


def _bot(ctx: AgentContext) -> "PlanningBot":
    bot = ctx.extras.get("bot")
    if bot is None:
        raise RuntimeError("planning bot missing in AgentContext.extras")
    return bot


@tool(category="tasks", always=True)
async def get_kanban(ctx: AgentContext, column: Optional[str] = None) -> str:
    """Kanban board snapshot (all columns or one)."""
    from planning_bot.core.config import KANBAN_COLUMNS, DONE_COLUMN

    bot = _bot(ctx)
    from shared.agent.platform_config import platform_int

    bot.kanban.load()
    tasks = bot.kanban.get_tasks(exclude_today=False, exclude_blocked=False)
    done_preview = max(1, platform_int("planning", "kanban_done_preview_max", default=1000))

    from planning_bot.services.reference_date import format_deadline_hint, reference_today_iso

    today = reference_today_iso()

    def fmt(t: dict) -> str:
        tid = t.get("task_id") or "—"
        pri = t.get("priority") or "—"
        cat = t.get("category") or "—"
        dl = format_deadline_hint(t.get("deadline"), today)
        done = pdmsg("agent_task_done_suffix") if t.get("completed") else ""
        return f"  [{tid}] [{pri}] {t.get('title', '')} | {cat}{dl}{done}"

    from planning_bot.services.kanban_agent import resolve_column_name

    if column:
        resolved = resolve_column_name(column)
        cols = [resolved] if resolved else KANBAN_COLUMNS
    else:
        cols = KANBAN_COLUMNS
    lines: list[str] = [
        pdmsg("agent_kanban_today_anchor", today=today),
        pdmsg("agent_kanban_today_hint"),
        pdmsg("agent_kanban_board_header"),
    ]
    for col in cols:
        all_col = [t for t in tasks if t.get("column") == col]
        col_tasks = all_col
        if col == DONE_COLUMN and len(all_col) > done_preview:
            col_tasks = sorted(
                all_col,
                key=lambda t: (t.get("created_date") or "", t.get("task_id") or ""),
                reverse=True,
            )[:done_preview]
            lines.append(
                pdmsg("agent_kanban_col_truncated", col=col, total=len(all_col), preview=done_preview)
            )
        else:
            lines.append(pdmsg("agent_kanban_col_count", col=col, count=len(col_tasks)))
        lines.extend(fmt(t) for t in col_tasks) if col_tasks else lines.append(pdmsg("agent_kanban_empty"))
    return "\n".join(lines)


@tool(category="goals")
async def get_goals(ctx: AgentContext) -> str:
    """Year goals, quarterly focus, and goals context."""
    bot = _bot(ctx)
    parts: list[str] = []
    try:
        goals = bot.goals_manager.get_goals()
        if goals:
            parts.append(pdmsg("agent_goals_year_header") + "\n".join(f"- {g}" for g in goals))
    except Exception as e:
        log.debug("goals failed: %s", e)
    try:
        qf = bot.goals_manager.get_quarterly_focus()
        if qf:
            parts.append(pdmsg("agent_goals_quarter_header") + "\n".join(f"- {g}" for g in qf))
    except Exception as e:
        log.debug("quarterly failed: %s", e)
    try:
        gc = bot.goals_manager.get_goals_context_what_to_do_only()
        if gc:
            parts.append(pdmsg("agent_goals_context_header") + gc)
    except Exception as e:
        log.debug("goals_context failed: %s", e)
    return "\n\n".join(parts) or pdmsg("agent_goals_empty")


@tool(category="calendar")
async def get_calendar(
    ctx: AgentContext,
    day: str = "",
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    hours_ahead: int = 48,
) -> str:
    """Calendar events: day=YYYY-MM-DD; or from_date/to_date/days list; else upcoming hours_ahead."""
    from planning_bot.core.config import CALENDAR_JSON_FILE
    from planning_bot.services.calendar_service import get_calendar_for_tool

    try:
        return get_calendar_for_tool(
            CALENDAR_JSON_FILE,
            day=day,
            from_date=from_date,
            to_date=to_date,
            days=days,
            hours_ahead=hours_ahead,
        )
    except Exception as e:
        log.debug("calendar failed: %s", e)
        return pdmsg("agent_calendar_unavailable")


@tool(category="health")
async def get_health_snapshot(ctx: AgentContext, day: str = "") -> str:
    """Health/Watch (IPhone/*.txt): one evening snapshot. day=YYYY-MM-DD; empty = latest."""
    from planning_bot.services.health_data import format_health_snapshot

    return format_health_snapshot(day)


@tool(category="health")
async def get_health_series(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    fields: Optional[List[str]] = None,
    days: int = 14,
) -> str:
    """Health/Watch: daily series: numeric table + text_fields table when present. from/to YYYY-MM-DD or days if dates empty."""

    from planning_bot.services.health_data import format_health_series

    default_days = max(1, min(int(days or 14), 90))
    return format_health_series(from_date, to_date, fields, default_days=default_days)


@tool(category="health")
async def get_health_summary(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
) -> str:
    """Health/Watch: avg/min/max over period + text_fields table (from/to YYYY-MM-DD)."""
    from planning_bot.services.health_data import format_health_summary

    return format_health_summary(from_date, to_date)


@tool(category="health")
async def get_health_anomalies(ctx: AgentContext, lookback_days: int = 30) -> str:
    """Health/Watch: latest day vs baseline over lookback_days (z-score)."""
    from planning_bot.services.health_data import format_health_anomalies

    return format_health_anomalies(lookback_days=lookback_days)


@tool(category="health")
async def get_health_correlations(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    fields: Optional[List[str]] = None,
) -> str:
    """Health/Watch: Pearson correlations between metrics (not causation)."""
    from planning_bot.services.health_data import format_health_correlations

    return format_health_correlations(from_date, to_date, fields)


@tool(category="health")
async def export_health_dataset(ctx: AgentContext, max_days: int = 0) -> str:
    """Export daily health dataset to CSV under dashboards data/actions."""
    from planning_bot.core.config import IPHONE_CONTEXT_DIR
    from planning_bot.services.health_data import export_health_daily_csv

    out = IPHONE_CONTEXT_DIR.parent / "health_daily.csv"
    n, path = export_health_daily_csv(out, max_days=max_days or None)
    return pdmsg("agent_health_export", n=n, path=path)


@tool(category="context")
async def get_mac_context(ctx: AgentContext, day: str = "") -> str:
    """Mac: one snapshot (latest or day=YYYY-MM-DD). For a time range use get_mac_snapshots."""
    from planning_bot.services.mac_context_query import format_mac_snapshot

    return format_mac_snapshot(day)


@tool(category="context")
async def get_mac_series(ctx: AgentContext, from_date: str = "", to_date: str = "") -> str:
    """Mac: one row per calendar day (last snap that day). Timeline → get_mac_snapshots(from_ts, to_ts)."""
    from planning_bot.services.mac_context_query import format_mac_series

    return format_mac_series(from_date, to_date)


@tool(category="context")
async def get_mac_snapshots(
    ctx: AgentContext,
    from_ts: str = "",
    to_ts: str = "",
    limit: int = 120,
    on_app_change_only: bool = False,
) -> str:
    """Mac snapshots in interval: from_ts/to_ts ISO (date or YYYY-MM-DDTHH:MM). ~5 min cadence; limit≤500, 0=all."""
    from planning_bot.services.mac_context_query import format_mac_snapshots

    return format_mac_snapshots(
        from_ts,
        to_ts,
        limit=limit,
        on_app_change_only=on_app_change_only,
    )


@tool(category="tasks", always=True)
async def search_tasks(
    ctx: AgentContext,
    query: str = "",
    column: str = "",
    category: str = "",
    priority: str = "",
    deadline_from: str = "",
    deadline_to: str = "",
    completed: Optional[bool] = None,
    limit: int = 25,
) -> str:
    """Search kanban tasks: text, column, category tag, priority, deadline, completed."""
    from planning_bot.services.kanban_agent import filter_tasks, format_task_list

    bot = _bot(ctx)
    bot.kanban.load()
    tasks = bot.kanban.get_tasks(exclude_today=False, exclude_blocked=False)
    matched = filter_tasks(
        tasks,
        query=query,
        column=column,
        category=category,
        priority=priority,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        completed=completed,
        limit=limit,
    )
    return format_task_list(matched, header=pdmsg("agent_tasks_filter_header"))


@tool(category="tasks", always=True)
async def apply_kanban_task(
    ctx: AgentContext,
    action: str,
    dry_run: bool = False,
    task_id: str = "",
    title: str = "",
    category: str = DEFAULT_CATEGORY,
    priority: str = DEFAULT_PRIORITY,
    column: str = "",
    all_matching: bool = False,
) -> str:
    """Board mutation: create | move | complete (KANBAN_AGENT_WRITES=1)."""
    from planning_bot.services.kanban_agent import apply_kanban_action

    bot = _bot(ctx)
    logger = bot.logger
    return apply_kanban_action(
        bot.kanban,
        action=action,
        dry_run=dry_run,
        task_id=task_id,
        title=title,
        category=category,
        priority=priority,
        column=column,
        all_matching=all_matching,
        logger=logger,
    )


@tool(category="calendar")
async def get_calendar_analytics(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    anchor: str = "",
) -> str:
    """Calendar analytics: totals, tags, and per-day meetings/minutes table (from/to, anchor)."""
    from datetime import date as date_cls

    from planning_bot.core.config import CALENDAR_JSON_FILE
    from planning_bot.services.calendar_analytics import compute_week_analytics
    from shared.parsing.date_range import resolve_date_range

    if not CALENDAR_JSON_FILE.exists():
        return pdmsg("agent_calendar_analytics_unavailable")
    import json

    data = json.loads(CALENDAR_JSON_FILE.read_text(encoding="utf-8"))
    events = data.get("events") or []
    dr = resolve_date_range(
        from_date=from_date,
        to_date=to_date,
        days=0,
        default_days=7,
        anchor=date_cls.today(),
    )
    anchor_d = date_cls.fromisoformat(anchor[:10]) if (anchor or "").strip() else (dr.start or date_cls.today())
    if dr.end and dr.start:
        horizon = max(1, min(90, (dr.end - anchor_d).days + 1))
    else:
        horizon = 7
    analytics = compute_week_analytics(events, anchor_d, horizon_days=horizon)
    lines = [
        pdmsg("agent_calendar_analytics_header", anchor=anchor_d.isoformat(), horizon=horizon),
        pdmsg("agent_calendar_analytics_minutes", minutes=analytics.get("totals", {}).get("window_meeting_minutes", 0)),
    ]
    tags = analytics.get("tags_top5") or []
    if tags:
        lines.append(pdmsg("agent_calendar_analytics_tags", tags=", ".join(f"{t[0]}:{t[1]}" for t in tags[:5])))
    life = analytics.get("life_top5") or []
    if life:
        lines.append(pdmsg("agent_calendar_analytics_sections", sections=", ".join(f"{a}:{b}h" for a, b in life[:5])))
    day_rows = analytics.get("days") or []
    if day_rows:
        lines.append(pdmsg("agent_calendar_analytics_daily_header"))
        lines.append(pdmsg("agent_calendar_analytics_daily_columns"))
        for row in day_rows:
            lines.append(
                pdmsg(
                    "agent_calendar_analytics_daily_row",
                    date=row.get("date", ""),
                    weekday=row.get("weekday", ""),
                    meetings=row.get("meeting_count", 0),
                    minutes=row.get("meeting_minutes", 0),
                )
            )
    return "\n".join(lines)


@tool(category="routines")
async def get_routines_status(ctx: AgentContext, day: str = "") -> str:
    """Routines checklist: day=YYYY-MM-DD (today file or history); empty = today."""
    from planning_bot.services.routines_status_query import format_routines_status

    return format_routines_status(day)


@tool(category="reflection")
async def get_activity_events(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    event_type: str = "",
    task_id: str = "",
    task_title: str = "",
    limit: int = 40,
) -> str:
    """Action log: ISO timestamp per line. event_type=completed|created|moved; limit=0 full window, else ≤1000 (default 40)."""
    from planning_bot.services.activity_log_query import (
        clamp_activity_limit,
        fetch_activity_events,
        format_activity_events_block,
    )
    from shared.query.agent_interval import IntervalMode, resolve_agent_interval

    bot = _bot(ctx)
    if bot.logger is None:
        return pdmsg("agent_action_log_unavailable")

    lim = clamp_activity_limit(limit)
    interval = resolve_agent_interval(
        from_date=from_date,
        to_date=to_date,
        days=days,
        default_days=30,
    )
    dr = interval.date_range if interval.mode == IntervalMode.DATE_RANGE else None
    if dr is None:
        from shared.parsing.date_range import resolve_date_range

        dr = resolve_date_range(default_days=30)
    et_raw = (event_type or "").strip().lower()
    event_types = {et_raw if et_raw.startswith("task_") else f"task_{et_raw}"} if et_raw else None
    filtered_label = next(iter(event_types)) if event_types else None

    entries, all_entries, n_raw, type_counts = fetch_activity_events(
        bot.logger,
        from_date=dr.start,
        to_date=dr.end,
        event_types=event_types,
        task_id=(task_id or "").strip() or None,
        task_title=(task_title or "").strip() or None,
        limit=lim,
    )
    if not entries and n_raw == 0:
        return pdmsg("agent_action_log_no_events")

    return format_activity_events_block(
        entries,
        all_entries,
        n_raw=n_raw,
        type_counts=type_counts,
        filtered_type=filtered_label,
        period_start=dr.start,
        period_end=dr.end,
    )


@tool(category="log", always=True)
async def get_action_log(
    ctx: AgentContext,
    day: str = "",
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    limit: int = 0,
) -> str:
    """Action log chain: day=YYYY-MM-DD; or from_date/to_date/days; else recent window. Filtered stats → get_activity_events."""
    from planning_bot.services.action_log_tool import format_action_log

    bot = _bot(ctx)
    if bot.logger is None:
        return pdmsg("agent_action_log_unavailable")
    try:
        out = format_action_log(
            bot.logger,
            day=day,
            from_date=from_date,
            to_date=to_date,
            days=days,
            limit=limit,
        )
        return out or pdmsg("agent_action_log_no_recent")
    except Exception as e:
        log.debug("action log failed: %s", e)
        return pdmsg("agent_action_log_unavailable")


def build_planning_registry() -> ToolRegistry:
    from shared.capabilities.registry import filter_planning_tools, register_tools
    from shared.memory.episodic import attach_memory_tools

    reg = ToolRegistry()
    register_tools(
        reg,
        filter_planning_tools(
            [
                get_kanban,
                search_tasks,
                apply_kanban_task,
                get_goals,
                get_calendar,
                get_calendar_analytics,
                get_health_snapshot,
                get_health_series,
                get_health_summary,
                get_health_anomalies,
                get_health_correlations,
                export_health_dataset,
                get_mac_context,
                get_mac_series,
                get_mac_snapshots,
                get_routines_status,
                get_activity_events,
                get_action_log,
            ]
        ),
    )
    attach_memory_tools(reg)
    return reg


class PlanningAdapter(DomainAdapter):
    domain = PLANNING_DOMAIN
    role = ModelRole.ANALYZE

    def __init__(self, bot: "PlanningBot") -> None:
        self._bot = bot

    def build_registry(self) -> ToolRegistry:
        return build_planning_registry()

    async def base_prompt(self, ctx: AgentContext) -> str:
        from planning_bot.core.settings import get_config_path, load_prompt
        from shared.agent.platform_config import agent_config_dir

        from planning_bot.services.reference_date import reference_now

        try:
            base = load_prompt(get_config_path(), "conversation")
        except Exception:
            base = pdmsg("agent_system_prompt_base")
        prompts_dir = agent_config_dir()
        from shared.capabilities.profile import (
            CONNECTOR_APPLE_HEALTH,
            CONNECTOR_MAC_CONTEXT,
            get_capabilities,
        )

        prof = get_capabilities()
        health_hint = ""
        if prof.connector(CONNECTOR_APPLE_HEALTH):
            health_hint = load_prompt(
                prompts_dir, "health_tools", subdir="prompts", required=False
            )
        context_hint = ""
        if prof.connector(CONNECTOR_MAC_CONTEXT):
            context_hint = load_prompt(
                prompts_dir, "context_tools", subdir="prompts", required=False
            )
        now = reference_now()
        date_hint = (
            pdmsg("agent_system_prompt_today", today=now.strftime("%Y-%m-%d (%A)"))
        )
        tools_hint = (
            pdmsg("agent_system_prompt_tools")
        )
        parts = [base, date_hint, tools_hint]
        if health_hint.strip():
            parts.append(health_hint.strip())
        if context_hint.strip():
            parts.append(context_hint.strip())
        parts.append(pdmsg("agent_system_prompt_format"))
        return "\n\n".join(parts)

    def memory_layers(self, ctx: AgentContext):
        from planning_bot.app.memory_layers import PlanningActionLogLayer
        from shared.memory.layers import build_memory_layers

        return [PlanningActionLogLayer(), *build_memory_layers(PLANNING_DOMAIN)]

    async def prepare_extras(self, user_id: int) -> dict:
        return {"bot": self._bot, "telegram_id": user_id}
