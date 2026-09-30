"""Planning agent tools for shared agent core."""
from __future__ import annotations

from planning_bot.core.config import DEFAULT_CATEGORY, DEFAULT_PRIORITY
from planning_bot.core.pdmsg import pdmsg
from planning_bot.app.task_tools import get_kanban, search_tasks, get_task_timeline, apply_kanban_task, get_recent_task_references

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
        body = get_calendar_for_tool(
            CALENDAR_JSON_FILE,
            day=day,
            from_date=from_date,
            to_date=to_date,
            days=days,
            hours_ahead=hours_ahead,
        )
        return body
    except Exception as e:
        log.debug("calendar failed: %s", e)
        return pdmsg("agent_calendar_unavailable")


from unified_bot.integrations.verifiers import calendar as verify_calendar

@tool(category="calendar", serial=True, mutating=True, verifier=verify_calendar)
async def create_calendar_event(ctx: AgentContext, title: str, start: str, end: str,
                                calendar: str = "", notes: str = "", location: str = "") -> str:
    """Create Apple Calendar event ONLY on user's explicit request; start/end ISO8601 with UTC offsets. Queued is NOT created; use get_calendar_event_status to verify. No invitations or recurrence."""
    import json
    from planning_bot.services.calendar_bridge import config, normalize, enqueue
    if not config().get("write_enabled"):
        return json.dumps({"status": "disabled"})
    try:
        payload = normalize(title, start, end, calendar, notes, location)
        return json.dumps(enqueue(ctx.user_id, payload), ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({"status": "invalid_request", "error": str(exc)})


@tool(category="calendar")
async def list_calendar_calendars(ctx: AgentContext) -> str:
    """List Apple Calendars with IDs and writable flag. Use an ID when calendar names are ambiguous."""
    import json
    from planning_bot.core.config import CALENDAR_JSON_FILE
    from planning_bot.services.calendar_freshness import describe_calendar
    try:
        data = json.loads(CALENDAR_JSON_FILE.read_text())
        return json.dumps({"freshness": describe_calendar(CALENDAR_JSON_FILE), "calendars": data.get("meta", {}).get("calendars", [])}, ensure_ascii=False)
    except (OSError, ValueError):
        return json.dumps({"status": "unavailable"})


@tool(category="calendar", read_only=True)
async def get_calendar_event_status(ctx: AgentContext, request_id: str) -> str:
    """Check own queued Apple Calendar creation. Only status=created with event_id confirms creation; never retry outcome_unknown as a new event."""
    import json
    from planning_bot.services.calendar_bridge import status
    return json.dumps(status(ctx.user_id, request_id), ensure_ascii=False)


@tool(category="health", read_only=True)
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
    """One computer-focus snapshot (latest or day=YYYY-MM-DD). Not a duration share over an interval."""
    from planning_bot.services.mac_context_query import format_mac_snapshot

    return format_mac_snapshot(day)


@tool(category="context")
async def get_mac_capture_summary(ctx: AgentContext, from_date: str = "", to_date: str = "") -> str:
    """Native Mac capture health and estimated active/idle/sleep time, unknown gaps, application duration. Dates YYYY-MM-DD in configured local timezone, inclusive. Use for duration questions; missing time is not activity."""
    import json
    from planning_bot.services.mac_capture import summary
    return json.dumps(summary(from_date, to_date), ensure_ascii=False)


@tool(category="context")
async def get_mac_series(ctx: AgentContext, from_date: str = "", to_date: str = "") -> str:
    """Last foreground app per calendar day. Not duration-weighted time share."""
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
    """Dense foreground log for an interval (from_ts/to_ts ISO). Duration-weighted category shares over ALL matches first; raw rows may be a tail (limit from config, 0=all)."""
    from planning_bot.services.mac_context_query import format_mac_snapshots

    return format_mac_snapshots(
        from_ts,
        to_ts,
        limit=limit,
        on_app_change_only=on_app_change_only,
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


@tool(category="routines", read_only=True)
async def get_routines_status(ctx: AgentContext, day: str = "") -> str:
    """Routines checklist: day=YYYY-MM-DD (today file or history); empty = today."""
    from planning_bot.services.routines_status_query import format_routines_status

    return format_routines_status(day)


@tool(category="routines")
async def get_daily_signals(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    limit: int = 14,
) -> str:
    """Subjective daily signals history (mood/energy/etc from check-in). from_date/to_date/days; default last 7 days."""
    from planning_bot.services.signals_query import format_daily_signals

    return format_daily_signals(
        from_date=from_date,
        to_date=to_date,
        days=days,
        limit=limit,
    )


@tool(category="reflection")
async def get_activity_events(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    event_type: str = "",
    task_id: str = "",
    task_title: str = "",
    limit: int = -1,
    summary: str = "auto",
) -> str:
    """Action log. limit=-1 auto (single day=full). summary=auto|unique|full|raw (auto→unique on one day)."""
    from planning_bot.services.activity_log_query import (
        fetch_activity_events,
        format_activity_events_block,
        resolve_activity_summary,
    )
    from shared.agent.budget_caps import resolve_activity_limit
    from shared.query.agent_interval import IntervalMode, resolve_agent_interval

    bot = _bot(ctx)
    if bot.logger is None:
        return pdmsg("agent_action_log_unavailable")

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

    lim = resolve_activity_limit(
        requested=int(limit),
        from_date=dr.start,
        to_date=dr.end,
    )
    mode = resolve_activity_summary(
        requested=summary,
        from_date=dr.start,
        to_date=dr.end,
    )
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
        summary=mode,
    )


@tool(category="tasks")
async def get_kanban_flow(ctx: AgentContext) -> str:
    """Kanban flow metrics: throughput, lead/cycle time, WIP segments vs goals mapping (from cached JSON)."""
    import json

    from planning_bot.core.config import VAULT_PATH
    from planning_bot.services.kanban_flow import format_kanban_flow_for_agent
    from shared.chart_paths import chart_path

    path = chart_path(VAULT_PATH, "kanban_flow_metrics_json")
    if not path.is_file():
        return pdmsg("kanban_flow_agent_no_data")
    try:
        metrics = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return pdmsg("kanban_flow_agent_no_data")
    return format_kanban_flow_for_agent(metrics, pdmsg)


@tool(category="log")
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


def _enrich_apply_kanban_tool(reg: ToolRegistry) -> None:
    """Inject kanban_schema categories into tool schema (no hardcoded labels in .py)."""
    from planning_bot.core.config import CATEGORIES, PRIORITIES

    try:
        t = reg.get("apply_kanban_task")
    except KeyError:
        return
    cats = list(CATEGORIES) if CATEGORIES else []
    prios = list(PRIORITIES) if PRIORITIES else []
    t.description = pdmsg(
        "apply_kanban_tool_hint",
        categories=", ".join(cats) if cats else DEFAULT_CATEGORY,
        priorities=", ".join(prios) if prios else DEFAULT_PRIORITY,
    )
    # Keep reference handling separate from personalized legacy tool hints.
    t.description += "\n" + pdmsg("kanban_reference_recovery_hint")
    props = dict(t.parameters.get("properties") or {})
    if cats:
        props["category"] = {"type": "string", "enum": cats}
    if prios:
        props["priority"] = {"type": "string", "enum": prios}
    t.parameters = {**t.parameters, "properties": props}


def build_planning_registry() -> ToolRegistry:
    from shared.capabilities.registry import filter_planning_tools, register_tools
    from shared.memory.episodic import attach_memory_tools
    from shared.agent.chart_tools import attach_chart_tools

    reg = ToolRegistry()
    register_tools(
        reg,
        filter_planning_tools(
            [
                get_kanban,
                get_recent_task_references,
                search_tasks,
                get_task_timeline,
                apply_kanban_task,
                get_goals,
                get_calendar,
                get_calendar_analytics,
                create_calendar_event,
                get_calendar_event_status,
                list_calendar_calendars,
                get_health_snapshot,
                get_health_series,
                get_health_summary,
                get_health_anomalies,
                get_health_correlations,
                export_health_dataset,
                get_mac_context,
                get_mac_capture_summary,
                get_mac_series,
                get_mac_snapshots,
                get_routines_status,
                get_daily_signals,
                get_activity_events,
                get_kanban_flow,
                get_action_log,
            ]
        ),
    )
    from shared.agent.series_tools import attach_series_tools

    _enrich_apply_kanban_tool(reg)
    attach_memory_tools(reg)
    attach_chart_tools(reg)
    attach_series_tools(reg)
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
        from planning_bot.services.reference_date import format_reference_today_label

        now = reference_now()
        date_hint = pdmsg(
            "agent_system_prompt_today",
            today=format_reference_today_label(),
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
