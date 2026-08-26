"""Build capabilities.yaml document from preset + connector toggles."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Optional

from shared.capabilities.compose import SYNC_PROFILE_AUTO, apply_sync_profile, merge_capability_overrides
from shared.capabilities.presets import PRESET_CUSTOM, PRESET_FULL, preset_document
from shared.capabilities.profile import (
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_KB_SERENDIPITY,
    CONNECTOR_MAC_CONTEXT,
    CONNECTOR_MANUAL_BROKER,
    CONNECTOR_DOMESTIC_BANK_CARDS,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    _ALL_CONNECTORS,
    _ALL_MODULES,
)


def _apply_connector_map(doc: dict[str, Any], updates: Mapping[str, bool]) -> None:
    block = doc.setdefault("connectors", {})
    for key, val in updates.items():
        if key in _ALL_CONNECTORS:
            block[key] = bool(val)


def _apply_module_map(doc: dict[str, Any], updates: Mapping[str, bool]) -> None:
    block = doc.setdefault("modules", {})
    for key, val in updates.items():
        if key in _ALL_MODULES:
            block[key] = bool(val)


def build_capabilities_document(
    preset: str = PRESET_FULL,
    *,
    modules: Optional[Mapping[str, bool]] = None,
    connectors: Optional[Mapping[str, bool]] = None,
    corporate_badge: Optional[bool] = None,
    broker_sync: Optional[bool] = None,
    apple_health: Optional[bool] = None,
    gmail_health: Optional[bool] = None,
    apple_calendar: Optional[bool] = None,
    mac_context: Optional[bool] = None,
    knowledge_serendipity: Optional[bool] = None,
    manual_broker: Optional[bool] = None,
    only_modules: Optional[list[str]] = None,
    sync_profile: Optional[str] = SYNC_PROFILE_AUTO,
) -> dict[str, Any]:
    """Merge preset (or custom blank) with explicit overrides; sync.profile defaults to auto."""
    key = (preset or PRESET_FULL).strip().lower()
    if only_modules:
        base = preset_document(PRESET_CUSTOM)
        mod_map = {m: m in only_modules for m in _ALL_MODULES}
        doc = merge_capability_overrides(base, modules=mod_map)
    else:
        doc = deepcopy(preset_document(key))
    if modules:
        _apply_module_map(doc, modules)
    connector_updates: dict[str, bool] = {}
    if connectors:
        connector_updates.update({k: bool(v) for k, v in connectors.items()})
    for key, val in (
        (CONNECTOR_CORPORATE_BADGE, corporate_badge),
        (CONNECTOR_BROKER_SYNC, broker_sync),
        (CONNECTOR_MANUAL_BROKER, manual_broker),
        (CONNECTOR_APPLE_HEALTH, apple_health),
        (CONNECTOR_GMAIL_HEALTH, gmail_health),
        (CONNECTOR_APPLE_CALENDAR, apple_calendar),
        (CONNECTOR_MAC_CONTEXT, mac_context),
        (CONNECTOR_KB_SERENDIPITY, knowledge_serendipity),
    ):
        if val is not None:
            connector_updates[key] = bool(val)
    if connector_updates:
        _apply_connector_map(doc, connector_updates)
    mod_block = doc.get("modules") or {}
    if mod_block.get(MODULE_FINANCE):
        con_block = doc.setdefault("connectors", {})
        for key in (CONNECTOR_MANUAL_BROKER, CONNECTOR_DOMESTIC_BANK_CARDS):
            if key not in con_block:
                con_block[key] = True
    apply_sync_profile(doc, sync_profile)
    return doc
