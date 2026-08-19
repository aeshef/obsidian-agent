"""Append capability-specific prompt lines when prod prompts lack @cap blocks."""
from __future__ import annotations

import os
from typing import Optional

from shared.capabilities.prompt_filter import capability_active
from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    get_capabilities,
)

# (cap_id, line) — same ids as <!-- @cap ... --> in *.example.txt
_HOST_LINES: tuple[tuple[str, str], ...] = (
    ("planning", "Kanban: create/move/complete via apply_kanban_task; get_kanban reads the board."),
    ("finance", "Finance: amounts and balances only from tools — do not invent numbers."),
    ("broker", "Broker portfolio sync is available for investment questions when configured."),
    ("badge", "Corporate meal badge limits may apply to food expenses when configured."),
    ("health", "Apple Health snapshots: use health tools with explicit day=YYYY-MM-DD."),
    ("body_metrics", "Body metrics include weight and body fat trends when present in snapshots."),
    ("gmail", "Gmail pipeline may deliver iPhone health shortcut emails into the vault."),
    ("calendar", "Calendar load and meeting analytics are available for planning questions."),
    ("knowledge", "Knowledge: search_knowledge_base and read_knowledge_note for documented notes."),
)

_HEALTH_LINES: tuple[tuple[str, str], ...] = (
    ("health", "Use health tools only; never guess metrics."),
    ("body_metrics", "Weight and body fat series come from snapshot tables when enabled."),
    ("gmail", "Gmail-delivered health files may supplement Apple Health exports."),
    ("nutrition", "Nutrition/KBJU charts require health_nutrition_chart feature."),
)

_TOOL_SELECT_LINES: tuple[tuple[str, str], ...] = (
    ("planning", "Kanban: apply_kanban_task; reads get_kanban, search_tasks (created_from/to, sort_by=created_asc), get_task_timeline."),
    ("finance", "Finance tools only for balances, transactions, plans — no invented numbers."),
    ("knowledge", "Knowledge: search_knowledge_base, read_knowledge_note."),
    ("broker", "Include broker tools only when investments/portfolio are in scope."),
    ("health", "Health snapshot tools need explicit day=YYYY-MM-DD."),
    ("calendar", "Calendar tools for scheduling and meeting analytics."),
)

_FINANCE_ROUTER_LINES: tuple[tuple[str, str], ...] = (
    ("finance", "Classify: new transaction vs data question vs chitchat."),
    ("badge", "Meal-badge expenses may need badge category from config."),
    ("broker", "Broker sync/top-up intents map to investment flows."),
)

_PLANNING_ROUTER_LINES: tuple[tuple[str, str], ...] = (
    ("planning", "Task create/move vs general planning chat."),
    ("calendar", "Calendar-heavy questions may need calendar tools."),
    ("health", "Health metrics questions use health tools, not guesses."),
)

_HOST_DOMAIN_LINES: tuple[tuple[str, str], ...] = (
    ("finance", "Route to finance when message is about money or accounts only."),
    ("planning", "Route to planning for tasks, kanban, goals, routines, completion logs."),
    ("knowledge", "Route to knowledge for notes and documented facts."),
    (
        "finance",
        "When money AND tasks/health/calendar are needed in one answer and allow_unified: use unified.",
    ),
)

_CONTEXT_LINES: tuple[tuple[str, str], ...] = (
    (
        "mac",
        "Mac interval log: time-in-app from duration-weighted shares over all matches; last-app-of-day is not time spent.",
    ),
)

_KNOWLEDGE_TOOLS_LINES: tuple[tuple[str, str], ...] = (
    ("knowledge", "Use knowledge tools; cite note titles from tool output only."),
)

_STEM_SUPPLEMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "host_query": _HOST_LINES,
    "health_tools": _HEALTH_LINES,
    "tool_select_router": _TOOL_SELECT_LINES,
    "finance_intent_router": _FINANCE_ROUTER_LINES,
    "planning_intent_router": _PLANNING_ROUTER_LINES,
    "host_domain_router": _HOST_DOMAIN_LINES,
    "context_tools": _CONTEXT_LINES,
    "knowledge_unified_tools": _KNOWLEDGE_TOOLS_LINES,
}


def _dynamic_supplement_enabled() -> bool:
    raw = os.environ.get("AGENT_PROMPT_DYNAMIC_SUPPLEMENT", "0").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _parent_module(cap_id: str) -> str | None:
    if cap_id in (
        "planning",
        "health",
        "body_metrics",
        "gmail",
        "calendar",
        "nutrition",
        "mac",
    ):
        return MODULE_PLANNING
    if cap_id in ("finance", "broker", "badge", "domestic_cards"):
        return MODULE_FINANCE
    if cap_id == "knowledge":
        return MODULE_KNOWLEDGE
    return None


def _line_visible(cap_id: str, profile: CapabilityProfile) -> bool:
    parent = _parent_module(cap_id)
    if parent and not profile.module(parent):
        return False
    if cap_id == "broker":
        from shared.capabilities.finance_gates import broker_sync_enabled

        return broker_sync_enabled()
    return capability_active(cap_id, profile)


def _lines_for_stem(stem: str, profile: CapabilityProfile) -> list[str]:
    spec = _STEM_SUPPLEMENTS.get(stem)
    if not spec:
        return []
    return [line for cap_id, line in spec if _line_visible(cap_id, profile)]


def augment_prompt_capabilities(
    stem: str,
    text: str,
    profile: Optional[CapabilityProfile] = None,
) -> str:
    """Append enabled capability hints when the prompt has no @cap blocks."""
    if not text or "<!-- @cap" in text or not _dynamic_supplement_enabled():
        return text
    prof = profile or get_capabilities()
    lines = _lines_for_stem(stem, prof)
    if not lines:
        return text
    block = "\n".join(f"- {ln}" for ln in lines)
    return f"{text.rstrip()}\n\n[Enabled capabilities]\n{block}".strip()


def clear_preamble_cache() -> None:
    """Reserved for future caching."""
