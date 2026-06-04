"""Named capability profiles for onboarding — no personal data."""
from __future__ import annotations

from typing import Any

from shared.capabilities.profile import (
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_MANUAL_BROKER,
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_KB_SERENDIPITY,
    CONNECTOR_MAC_CONTEXT,
    CONNECTOR_DOMESTIC_BANK_CARDS,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    SYNC_PROFILE_FINANCE_ONLY,
    SYNC_PROFILE_FULL,
    SYNC_PROFILE_MINIMAL,
    SYNC_PROFILE_PLANNING_KANBAN,
    SYNC_PROFILE_PLANNING_LIGHT,
    _default_document,
)

PRESET_FULL = "full"
PRESET_CUSTOM = "custom"
PRESET_FINANCE_ONLY = "finance_only"
PRESET_PLANNING_ONLY = "planning_only"
PRESET_PLANNING_LIGHT = "planning_light"
PRESET_MINIMAL = "minimal"

_ALL_OFF_CONNECTORS = {
    CONNECTOR_CORPORATE_BADGE: False,
    CONNECTOR_BROKER_SYNC: False,
    CONNECTOR_MANUAL_BROKER: False,
    CONNECTOR_APPLE_HEALTH: False,
    CONNECTOR_GMAIL_HEALTH: False,
    CONNECTOR_APPLE_CALENDAR: False,
    CONNECTOR_MAC_CONTEXT: False,
    CONNECTOR_KB_SERENDIPITY: False,
    CONNECTOR_DOMESTIC_BANK_CARDS: False,
}


def _doc(
    *,
    modules: dict[str, bool],
    connectors: dict[str, bool] | None = None,
    sync_profile: str = SYNC_PROFILE_FULL,
) -> dict[str, Any]:
    base = _default_document()
    base["modules"] = {m: modules.get(m, False) for m in (MODULE_FINANCE, MODULE_PLANNING, MODULE_KNOWLEDGE)}
    if connectors is not None:
        base["connectors"] = {**_ALL_OFF_CONNECTORS, **connectors}
    base["sync"] = {"profile": sync_profile}
    return base


PRESET_DOCUMENTS: dict[str, dict[str, Any]] = {
    PRESET_FULL: _default_document(),
    PRESET_CUSTOM: _doc(
        modules={MODULE_FINANCE: False, MODULE_PLANNING: False, MODULE_KNOWLEDGE: False},
        connectors=_ALL_OFF_CONNECTORS.copy(),
        sync_profile=SYNC_PROFILE_MINIMAL,
    ),
    PRESET_PLANNING_ONLY: _doc(
        modules={MODULE_FINANCE: False, MODULE_PLANNING: True, MODULE_KNOWLEDGE: False},
        connectors=_ALL_OFF_CONNECTORS.copy(),
        sync_profile=SYNC_PROFILE_PLANNING_KANBAN,
    ),
    PRESET_FINANCE_ONLY: _doc(
        modules={MODULE_FINANCE: True, MODULE_PLANNING: False, MODULE_KNOWLEDGE: False},
        connectors={
            **_ALL_OFF_CONNECTORS,
            CONNECTOR_MANUAL_BROKER: True,
            CONNECTOR_DOMESTIC_BANK_CARDS: True,
        },
        sync_profile=SYNC_PROFILE_FINANCE_ONLY,
    ),
    PRESET_PLANNING_LIGHT: _doc(
        modules={MODULE_FINANCE: False, MODULE_PLANNING: True, MODULE_KNOWLEDGE: False},
        connectors={
            **_ALL_OFF_CONNECTORS,
            CONNECTOR_APPLE_HEALTH: True,
            CONNECTOR_GMAIL_HEALTH: True,
            CONNECTOR_APPLE_CALENDAR: True,
            CONNECTOR_MAC_CONTEXT: True,
        },
        sync_profile=SYNC_PROFILE_PLANNING_LIGHT,
    ),
    PRESET_MINIMAL: _doc(
        modules={MODULE_FINANCE: True, MODULE_PLANNING: False, MODULE_KNOWLEDGE: False},
        connectors=_ALL_OFF_CONNECTORS.copy(),
        sync_profile=SYNC_PROFILE_MINIMAL,
    ),
}


def list_preset_names() -> tuple[str, ...]:
    return tuple(PRESET_DOCUMENTS.keys())


def preset_document(name: str) -> dict[str, Any]:
    key = (name or "").strip().lower()
    if key not in PRESET_DOCUMENTS:
        raise KeyError(f"unknown preset {name!r}; choose from {list(PRESET_DOCUMENTS)}")
    return PRESET_DOCUMENTS[key]
