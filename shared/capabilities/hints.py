"""Dynamic domain_hints for tool-select — only mention enabled capabilities."""
from __future__ import annotations

from functools import lru_cache

from shared.capabilities.features import FEAT_HEALTH_BODY, FEAT_HEALTH_NUTRITION, feature_enabled
from shared.capabilities.profile import (
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_DOMESTIC_BANK_CARDS,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_MAC_CONTEXT,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    get_capabilities,
)


def _hint_finance(prof) -> str:
    parts = [
        "money operations and summaries",
        "dashboard chart PNGs via list_vault_charts/send_vault_charts",
    ]
    if prof.connector(CONNECTOR_BROKER_SYNC):
        parts.append("broker portfolio")
    if prof.connector(CONNECTOR_CORPORATE_BADGE):
        parts.append("corporate meal badge")
    if prof.connector(CONNECTOR_DOMESTIC_BANK_CARDS):
        parts.append("domestic card/wallet balances")
    return "; ".join(parts)


def _hint_planning(prof) -> str:
    parts = [
        "tasks",
        "goals",
        "kanban create/move/complete via apply_kanban_task",
        "dashboard chart PNGs via list_vault_charts/send_vault_charts",
    ]
    if prof.connector(CONNECTOR_APPLE_CALENDAR):
        parts.append("calendar")
    if prof.connector(CONNECTOR_APPLE_HEALTH):
        health_bits = []
        if feature_enabled(FEAT_HEALTH_NUTRITION, prof):
            health_bits.append("nutrition")
        if feature_enabled(FEAT_HEALTH_BODY, prof):
            health_bits.append("body metrics")
        parts.append(
            "Apple Health (" + ", ".join(health_bits) + ")"
            if health_bits
            else "Apple Health"
        )
    if prof.connector(CONNECTOR_GMAIL_HEALTH):
        parts.append("Gmail → health snapshots")
    if prof.connector(CONNECTOR_MAC_CONTEXT):
        parts.append("Mac focus snapshots")
    parts.append("task action log")
    return "; ".join(parts)


def _hint_knowledge(_prof) -> str:
    return "named note read_knowledge_note; topic overview search_knowledge_base"


def _hint_unified(prof) -> str:
    enabled = prof.enabled_modules()
    bits = []
    if MODULE_FINANCE in enabled:
        bits.append(_hint_finance(prof))
    if MODULE_PLANNING in enabled:
        bits.append(_hint_planning(prof))
    if MODULE_KNOWLEDGE in enabled:
        bits.append(_hint_knowledge(prof))
    if len(enabled) >= 2:
        bits.append("cross-domain queries with explicit date ranges")
    bits.append("dashboard chart PNGs via list_vault_charts/send_vault_charts")
    return "; ".join(bits) if bits else "general assistant"


@lru_cache(maxsize=8)
def domain_hint_text(domain: str) -> str:
    prof = get_capabilities()
    if domain == MODULE_FINANCE and prof.module(MODULE_FINANCE):
        return _hint_finance(prof)
    if domain == MODULE_PLANNING and prof.module(MODULE_PLANNING):
        return _hint_planning(prof)
    if domain == MODULE_KNOWLEDGE and prof.module(MODULE_KNOWLEDGE):
        return _hint_knowledge(prof)
    if domain == "unified":
        return _hint_unified(prof)
    from shared.agent.config import load_tools_config

    static = (load_tools_config().get("domain_hints") or {}).get(domain) or ""
    return static


def clear_hints_cache() -> None:
    domain_hint_text.cache_clear()
