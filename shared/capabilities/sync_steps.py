"""obsidian_sync.sh optional steps — gated by sync profile + connectors."""
from __future__ import annotations

from typing import Optional

from shared.capabilities.features import (
    FEAT_HEALTH_BODY,
    FEAT_HEALTH_NUTRITION,
    feature_enabled,
)
from shared.capabilities.profile import (
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_KB_SERENDIPITY,
    CONNECTOR_MAC_CONTEXT,
    SYNC_PROFILE_FINANCE_ONLY,
    SYNC_PROFILE_FULL,
    SYNC_PROFILE_KNOWLEDGE_ONLY,
    SYNC_PROFILE_MINIMAL,
    SYNC_PROFILE_PLANNING_LIGHT,
    SYNC_PROFILE_PLANNING_KANBAN,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    _ENV_MODULE,
    _ALL_MODULES,
    get_capabilities,
)

# Shell env vars (export_capabilities_env.py)
STEP_MAC_IPHONE = "CAP_SYNC_MAC_IPHONE"
STEP_GMAIL_HEALTH = "CAP_SYNC_GMAIL_HEALTH"
STEP_PLANNING_CHARTS = "CAP_SYNC_PLANNING_CHARTS"
STEP_CALENDAR = "CAP_SYNC_CALENDAR"
STEP_NUTRITION = "CAP_SYNC_NUTRITION"
STEP_HEALTH_ANALYTICS = "CAP_SYNC_HEALTH_ANALYTICS"
STEP_CROSS_ANALYTICS = "CAP_SYNC_CROSS_ANALYTICS"
STEP_KB_MAINTENANCE = "CAP_SYNC_KB_MAINTENANCE"
STEP_FINANCE_DASHBOARD = "CAP_SYNC_FINANCE_DASHBOARD"
STEP_VAULT_AUDIT_HEAVY = "CAP_SYNC_VAULT_AUDIT_HEAVY"

_ALL_STEPS = (
    STEP_MAC_IPHONE,
    STEP_GMAIL_HEALTH,
    STEP_PLANNING_CHARTS,
    STEP_CALENDAR,
    STEP_NUTRITION,
    STEP_HEALTH_ANALYTICS,
    STEP_CROSS_ANALYTICS,
    STEP_KB_MAINTENANCE,
    STEP_FINANCE_DASHBOARD,
    STEP_VAULT_AUDIT_HEAVY,
)

_PROFILE_DEFAULTS: dict[str, dict[str, bool]] = {
    SYNC_PROFILE_FULL: {s: True for s in _ALL_STEPS},
    SYNC_PROFILE_FINANCE_ONLY: {
        STEP_MAC_IPHONE: False,
        STEP_GMAIL_HEALTH: False,
        STEP_PLANNING_CHARTS: False,
        STEP_CALENDAR: False,
        STEP_NUTRITION: False,
        STEP_HEALTH_ANALYTICS: False,
        STEP_CROSS_ANALYTICS: False,
        STEP_KB_MAINTENANCE: False,
        STEP_FINANCE_DASHBOARD: True,
        STEP_VAULT_AUDIT_HEAVY: False,
    },
    SYNC_PROFILE_PLANNING_LIGHT: {
        STEP_MAC_IPHONE: True,
        STEP_GMAIL_HEALTH: True,
        STEP_PLANNING_CHARTS: True,
        STEP_CALENDAR: True,
        STEP_NUTRITION: True,
        STEP_HEALTH_ANALYTICS: True,
        STEP_CROSS_ANALYTICS: True,
        STEP_KB_MAINTENANCE: False,
        STEP_FINANCE_DASHBOARD: False,
        STEP_VAULT_AUDIT_HEAVY: False,
    },
    SYNC_PROFILE_MINIMAL: {
        STEP_MAC_IPHONE: False,
        STEP_GMAIL_HEALTH: False,
        STEP_PLANNING_CHARTS: False,
        STEP_CALENDAR: False,
        STEP_NUTRITION: False,
        STEP_HEALTH_ANALYTICS: False,
        STEP_CROSS_ANALYTICS: False,
        STEP_KB_MAINTENANCE: False,
        STEP_FINANCE_DASHBOARD: True,
        STEP_VAULT_AUDIT_HEAVY: False,
    },
    SYNC_PROFILE_PLANNING_KANBAN: {
        STEP_MAC_IPHONE: False,
        STEP_GMAIL_HEALTH: False,
        STEP_PLANNING_CHARTS: True,
        STEP_CALENDAR: False,
        STEP_NUTRITION: False,
        STEP_HEALTH_ANALYTICS: False,
        STEP_CROSS_ANALYTICS: False,
        STEP_KB_MAINTENANCE: False,
        STEP_FINANCE_DASHBOARD: False,
        STEP_VAULT_AUDIT_HEAVY: False,
    },
    SYNC_PROFILE_KNOWLEDGE_ONLY: {
        STEP_MAC_IPHONE: False,
        STEP_GMAIL_HEALTH: False,
        STEP_PLANNING_CHARTS: False,
        STEP_CALENDAR: False,
        STEP_NUTRITION: False,
        STEP_HEALTH_ANALYTICS: False,
        STEP_CROSS_ANALYTICS: False,
        STEP_KB_MAINTENANCE: True,
        STEP_FINANCE_DASHBOARD: False,
        STEP_VAULT_AUDIT_HEAVY: True,
    },
}


def _profile_step_default(profile: CapabilityProfile, step: str) -> bool:
    name = profile.sync_profile
    block = _PROFILE_DEFAULTS.get(name) or _PROFILE_DEFAULTS[SYNC_PROFILE_FULL]
    return bool(block.get(step, True))


def _connector_allows_step(profile: CapabilityProfile, step: str) -> bool:
    if step == STEP_FINANCE_DASHBOARD:
        return profile.module(MODULE_FINANCE)
    if step == STEP_PLANNING_CHARTS:
        return profile.module(MODULE_PLANNING)
    if step in (STEP_KB_MAINTENANCE, STEP_VAULT_AUDIT_HEAVY):
        return profile.module(MODULE_KNOWLEDGE)
    if step == STEP_GMAIL_HEALTH:
        return profile.connector(CONNECTOR_GMAIL_HEALTH)
    if step == STEP_CALENDAR:
        return profile.connector(CONNECTOR_APPLE_CALENDAR) and profile.module(MODULE_PLANNING)
    if step in (STEP_MAC_IPHONE, STEP_NUTRITION, STEP_HEALTH_ANALYTICS):
        if not profile.module(MODULE_PLANNING):
            return False
        if step == STEP_NUTRITION:
            return profile.connector(CONNECTOR_APPLE_HEALTH) and feature_enabled(
                FEAT_HEALTH_NUTRITION, profile
            )
        if step == STEP_HEALTH_ANALYTICS:
            return profile.connector(CONNECTOR_APPLE_HEALTH)
        return profile.connector(CONNECTOR_MAC_CONTEXT) or profile.connector(
            CONNECTOR_APPLE_HEALTH
        )
    if step == STEP_CROSS_ANALYTICS:
        return profile.any_module(MODULE_PLANNING, MODULE_FINANCE) and profile.connector(
            CONNECTOR_APPLE_HEALTH
        )
    return True


def sync_step_enabled(step: str, profile: Optional[CapabilityProfile] = None) -> bool:
    prof = profile or get_capabilities()
    if step not in _ALL_STEPS:
        return True
    if not _profile_step_default(prof, step):
        return False
    return _connector_allows_step(prof, step)


def export_shell_env(profile: Optional[CapabilityProfile] = None) -> str:
    """Emit export CAP_SYNC_* and CAP_MODULE_* for obsidian_sync.sh eval."""
    from shlex import quote

    allowed = frozenset(
        {
            SYNC_PROFILE_FULL,
            SYNC_PROFILE_FINANCE_ONLY,
            SYNC_PROFILE_PLANNING_LIGHT,
            SYNC_PROFILE_PLANNING_KANBAN,
            SYNC_PROFILE_KNOWLEDGE_ONLY,
            SYNC_PROFILE_MINIMAL,
        }
    )
    prof = profile or get_capabilities()
    sync_profile = prof.sync_profile if prof.sync_profile in allowed else SYNC_PROFILE_FULL
    lines = [
        f"export CAPABILITIES_SYNC_PROFILE={quote(sync_profile)}",
    ]
    for mod in _ALL_MODULES:
        env_name = _ENV_MODULE[mod]
        lines.append(f"export {env_name}={'1' if prof.module(mod) else '0'}")
    for step in _ALL_STEPS:
        val = "1" if sync_step_enabled(step, prof) else "0"
        lines.append(f"export {step}={val}")
    lines.append(
        f"export CAP_FEATURE_HEALTH_BODY_METRICS={'1' if feature_enabled(FEAT_HEALTH_BODY, prof) else '0'}"
    )
    lines.append(
        f"export CAP_FEATURE_HEALTH_NUTRITION_CHART={'1' if feature_enabled(FEAT_HEALTH_NUTRITION, prof) else '0'}"
    )
    return "\n".join(lines) + "\n"


def vault_rsync_300_enabled(profile: Optional[CapabilityProfile] = None) -> bool:
    """Dashboards folder: finance.db, charts, logs — any active product module may use it."""
    prof = profile or get_capabilities()
    return prof.any_module(MODULE_FINANCE, MODULE_PLANNING, MODULE_KNOWLEDGE)
