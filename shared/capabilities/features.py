"""Optional fine-grained flags (capabilities.yaml `features:`). Missing keys inherit from modules/connectors."""
from __future__ import annotations

from typing import Mapping, Optional

from shared.capabilities.profile import (
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_BROKER_SYNC,
    MODULE_FINANCE,
    MODULE_PLANNING,
    CapabilityProfile,
    _as_bool,
    get_capabilities,
)

# Health (require planning + apple_health when unset)
FEAT_HEALTH_NUTRITION = "health_nutrition_chart"
FEAT_HEALTH_BODY = "health_body_metrics"

# Broker account kinds (require finance + broker_sync when unset)
FEAT_BROKER_REGULAR = "broker_regular"
FEAT_BROKER_IIS = "broker_iis"
FEAT_BROKER_INVEST_BOX = "broker_invest_box"

# Planning APScheduler jobs (require planning module when unset)
FEAT_PLANNING_WEEKLY_REVIEW = "planning_weekly_review"
FEAT_PLANNING_ROUTINES = "planning_routines"
FEAT_PLANNING_GOALS_ALERTS = "planning_goals_alerts"
FEAT_PLANNING_DEADLINES = "planning_deadlines_alerts"
FEAT_PLANNING_STUCK = "planning_stuck_alerts"
FEAT_PLANNING_TASK_IDS = "planning_task_id_maintenance"

ALL_FEATURE_KEYS = (
    FEAT_HEALTH_NUTRITION,
    FEAT_HEALTH_BODY,
    FEAT_BROKER_REGULAR,
    FEAT_BROKER_IIS,
    FEAT_BROKER_INVEST_BOX,
    FEAT_PLANNING_WEEKLY_REVIEW,
    FEAT_PLANNING_ROUTINES,
    FEAT_PLANNING_GOALS_ALERTS,
    FEAT_PLANNING_DEADLINES,
    FEAT_PLANNING_STUCK,
    FEAT_PLANNING_TASK_IDS,
)

_ALL_FEATURE_KEYS = ALL_FEATURE_KEYS

_ENV_FEATURE = {k: f"CAP_FEATURE_{k.upper()}" for k in ALL_FEATURE_KEYS}


def _parent_default(profile: CapabilityProfile, key: str) -> bool:
    if key in (FEAT_HEALTH_NUTRITION, FEAT_HEALTH_BODY):
        return profile.module(MODULE_PLANNING) and profile.connector(CONNECTOR_APPLE_HEALTH)
    if key in (FEAT_BROKER_REGULAR, FEAT_BROKER_IIS, FEAT_BROKER_INVEST_BOX):
        return profile.module(MODULE_FINANCE) and profile.connector(CONNECTOR_BROKER_SYNC)
    if key.startswith("planning_"):
        return profile.module(MODULE_PLANNING)
    return True


def parse_feature_overrides(raw: object) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, bool] = {}
    for key in ALL_FEATURE_KEYS:
        if key in raw:
            out[key] = _as_bool(raw[key], True)
    return out


def apply_feature_env_overrides(overrides: dict[str, bool]) -> None:
    import os

    for key, env_name in _ENV_FEATURE.items():
        raw = os.environ.get(env_name)
        if raw is not None and str(raw).strip() != "":
            overrides[key] = _as_bool(raw, overrides.get(key, True))


def feature_enabled(name: str, profile: Optional[CapabilityProfile] = None) -> bool:
    prof = profile or get_capabilities()
    if name in prof.feature_overrides:
        return bool(prof.feature_overrides[name])
    return _parent_default(prof, name)


def broker_api_kind(api_type_name: Optional[str]) -> str:
    t = (api_type_name or "").strip()
    if t == "ACCOUNT_TYPE_TINKOFF_IIS":
        return FEAT_BROKER_IIS
    if t == "ACCOUNT_TYPE_INVEST_BOX":
        return FEAT_BROKER_INVEST_BOX
    return FEAT_BROKER_REGULAR
