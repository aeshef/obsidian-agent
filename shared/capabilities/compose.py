"""Compose capabilities.yaml from explicit module/connector choices (no fixed personas)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Optional

from shared.capabilities.profile import (
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_MAC_CONTEXT,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    SYNC_PROFILE_FINANCE_ONLY,
    SYNC_PROFILE_FULL,
    SYNC_PROFILE_KNOWLEDGE_ONLY,
    SYNC_PROFILE_MINIMAL,
    SYNC_PROFILE_PLANNING_KANBAN,
    SYNC_PROFILE_PLANNING_LIGHT,
    _ALL_CONNECTORS,
    _ALL_MODULES,
)

SYNC_PROFILE_AUTO = "auto"


def _module_map(doc: dict[str, Any]) -> dict[str, bool]:
    raw = doc.get("modules") if isinstance(doc.get("modules"), dict) else {}
    return {m: bool(raw.get(m, False)) for m in _ALL_MODULES}


def _connector_map(doc: dict[str, Any]) -> dict[str, bool]:
    raw = doc.get("connectors") if isinstance(doc.get("connectors"), dict) else {}
    return {c: bool(raw.get(c, False)) for c in _ALL_CONNECTORS}


def infer_sync_profile(doc: dict[str, Any]) -> str:
    """Derive sync.profile from enabled modules/connectors (no hardcoded user persona)."""
    modules = _module_map(doc)
    connectors = _connector_map(doc)
    f = modules[MODULE_FINANCE]
    p = modules[MODULE_PLANNING]
    k = modules[MODULE_KNOWLEDGE]

    if f and not p and not k:
        return SYNC_PROFILE_FINANCE_ONLY
    if f and not p and k:
        return SYNC_PROFILE_MINIMAL
    if p and not f and not k:
        healthish = any(
            connectors.get(c)
            for c in (
                CONNECTOR_APPLE_HEALTH,
                CONNECTOR_GMAIL_HEALTH,
                CONNECTOR_APPLE_CALENDAR,
                CONNECTOR_MAC_CONTEXT,
            )
        )
        return SYNC_PROFILE_PLANNING_LIGHT if healthish else SYNC_PROFILE_PLANNING_KANBAN
    if p and f and not k:
        return SYNC_PROFILE_FULL
    if not f and not p and k:
        return SYNC_PROFILE_KNOWLEDGE_ONLY
    return SYNC_PROFILE_FULL


def apply_sync_profile(doc: dict[str, Any], sync_profile: Optional[str]) -> None:
    block = doc.setdefault("sync", {})
    raw = (sync_profile or SYNC_PROFILE_AUTO).strip().lower()
    if raw in ("", SYNC_PROFILE_AUTO, "infer"):
        block["profile"] = infer_sync_profile(doc)
    else:
        block["profile"] = raw


def compose_capabilities_document(
    *,
    modules: Mapping[str, bool],
    connectors: Optional[Mapping[str, bool]] = None,
    features: Optional[Mapping[str, bool]] = None,
    sync_profile: Optional[str] = SYNC_PROFILE_AUTO,
) -> dict[str, Any]:
    """Build manifest from explicit toggles (all keys must be known modules/connectors)."""
    doc: dict[str, Any] = {
        "modules": {m: bool(modules.get(m, False)) for m in _ALL_MODULES},
        "connectors": {c: bool((connectors or {}).get(c, False)) for c in _ALL_CONNECTORS},
    }
    if features:
        doc["features"] = {k: bool(v) for k, v in features.items()}
    apply_sync_profile(doc, sync_profile)
    return doc


def merge_capability_overrides(
    base: dict[str, Any],
    *,
    modules: Optional[Mapping[str, bool]] = None,
    connectors: Optional[Mapping[str, bool]] = None,
    features: Optional[Mapping[str, bool]] = None,
    sync_profile: Optional[str] = None,
) -> dict[str, Any]:
    doc = deepcopy(base)
    if modules:
        block = doc.setdefault("modules", {})
        for k, v in modules.items():
            if k in _ALL_MODULES:
                block[k] = bool(v)
    if connectors:
        block = doc.setdefault("connectors", {})
        for k, v in connectors.items():
            if k in _ALL_CONNECTORS:
                block[k] = bool(v)
    if features:
        block = doc.setdefault("features", {})
        block.update({k: bool(v) for k, v in features.items()})
    if sync_profile:
        apply_sync_profile(doc, sync_profile)
    return doc
