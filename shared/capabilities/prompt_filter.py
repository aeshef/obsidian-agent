"""Strip <!-- @cap id --> blocks from prod prompts when capability is off."""
from __future__ import annotations

import re
from typing import Optional

from shared.capabilities.features import ALL_FEATURE_KEYS, feature_enabled
from shared.capabilities.profile import (
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_DOMESTIC_BANK_CARDS,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_KB_SERENDIPITY,
    CONNECTOR_MAC_CONTEXT,
    CONNECTOR_MANUAL_BROKER,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    _ALL_CONNECTORS,
    _ALL_MODULES,
    get_capabilities,
)

_CAP_BLOCK = re.compile(
    r"<!--\s*@cap\s+([a-zA-Z0-9_.-]+)\s*-->\s*.*?<!--\s*@/cap\s*-->",
    re.DOTALL | re.IGNORECASE,
)

# Short aliases for prompt authors (map to module / connector / feature id).
_CAP_ALIASES: dict[str, str] = {
    "finance": MODULE_FINANCE,
    "planning": MODULE_PLANNING,
    "knowledge": MODULE_KNOWLEDGE,
    "badge": CONNECTOR_CORPORATE_BADGE,
    "corporate_badge": CONNECTOR_CORPORATE_BADGE,
    "broker": CONNECTOR_BROKER_SYNC,
    "broker_sync": CONNECTOR_BROKER_SYNC,
    "manual_broker": CONNECTOR_MANUAL_BROKER,
    "manual_broker_accounts": CONNECTOR_MANUAL_BROKER,
    "apple_health": CONNECTOR_APPLE_HEALTH,
    "health": CONNECTOR_APPLE_HEALTH,
    "gmail": CONNECTOR_GMAIL_HEALTH,
    "gmail_health": CONNECTOR_GMAIL_HEALTH,
    "gmail_health_pipeline": CONNECTOR_GMAIL_HEALTH,
    "calendar": CONNECTOR_APPLE_CALENDAR,
    "apple_calendar": CONNECTOR_APPLE_CALENDAR,
    "mac": CONNECTOR_MAC_CONTEXT,
    "mac_context": CONNECTOR_MAC_CONTEXT,
    "serendipity": CONNECTOR_KB_SERENDIPITY,
    "knowledge_serendipity": CONNECTOR_KB_SERENDIPITY,
    "domestic_cards": CONNECTOR_DOMESTIC_BANK_CARDS,
    "domestic_bank_cards": CONNECTOR_DOMESTIC_BANK_CARDS,
    "nutrition": "health_nutrition_chart",
    "body_metrics": "health_body_metrics",
    "health_body": "health_body_metrics",
}


def _resolve_cap_id(raw: str) -> str:
    key = (raw or "").strip().lower()
    return _CAP_ALIASES.get(key, key)


def capability_active(cap_id: str, profile: Optional[CapabilityProfile] = None) -> bool:
    prof = profile or get_capabilities()
    resolved = _resolve_cap_id(cap_id)
    if resolved in _ALL_MODULES:
        return prof.module(resolved)
    if resolved in _ALL_CONNECTORS:
        return prof.connector(resolved)
    if resolved in ALL_FEATURE_KEYS:
        return prof.feature(resolved)
    return True


def filter_prompt_capabilities(text: str, profile: Optional[CapabilityProfile] = None) -> str:
    if not text or "<!-- @cap" not in text:
        return text

    def _repl(match: re.Match[str]) -> str:
        cap_id = match.group(1)
        return match.group(0) if capability_active(cap_id, profile) else ""

    out = _CAP_BLOCK.sub(_repl, text)
    return re.sub(r"\n{3,}", "\n\n", out).strip()
