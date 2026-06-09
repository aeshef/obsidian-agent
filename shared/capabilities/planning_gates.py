"""Planning scheduler / startup gates."""
from __future__ import annotations

from shared.capabilities.features import (
    FEAT_PLANNING_DAILY_CHECKIN,
    FEAT_PLANNING_DEADLINES,
    FEAT_PLANNING_GOALS_ALERTS,
    FEAT_PLANNING_ROUTINES,
    FEAT_PLANNING_STUCK,
    FEAT_PLANNING_TASK_IDS,
    FEAT_PLANNING_WEEKLY_REVIEW,
    feature_enabled,
)
from shared.capabilities.profile import MODULE_PLANNING, get_capabilities


def planning_schedulers_enabled() -> bool:
    return get_capabilities().module(MODULE_PLANNING)


def planning_weekly_review_enabled() -> bool:
    return feature_enabled(FEAT_PLANNING_WEEKLY_REVIEW)


def planning_routines_enabled() -> bool:
    return feature_enabled(FEAT_PLANNING_ROUTINES)


def planning_daily_checkin_enabled() -> bool:
    return feature_enabled(FEAT_PLANNING_DAILY_CHECKIN)


def planning_goals_alerts_enabled() -> bool:
    return feature_enabled(FEAT_PLANNING_GOALS_ALERTS)


def planning_deadlines_alerts_enabled() -> bool:
    return feature_enabled(FEAT_PLANNING_DEADLINES)


def planning_stuck_alerts_enabled() -> bool:
    return feature_enabled(FEAT_PLANNING_STUCK)


def planning_task_id_maintenance_enabled() -> bool:
    return feature_enabled(FEAT_PLANNING_TASK_IDS)
