"""Classify kanban tasks by goals-mapping segment (config-driven categories)."""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional

SEGMENT_GOAL_MAPPED = "goal_mapped"
SEGMENT_UNMAPPED = "unmapped"
SEGMENT_DAILY_ROUTINE = "daily_routine"

ALL_SEGMENTS = (SEGMENT_GOAL_MAPPED, SEGMENT_UNMAPPED, SEGMENT_DAILY_ROUTINE)


def flow_daily_categories(schema: dict) -> FrozenSet[str]:
    fm = schema.get("flow_metrics") or {}
    raw = fm.get("daily_routine_categories") or []
    return frozenset(str(c).strip().lower() for c in raw if str(c).strip())


def classify_task_goal_segment(
    task_id: Optional[str],
    category: Optional[str],
    mapping: Dict[str, List[str]],
    daily_categories: FrozenSet[str],
) -> str:
    tid = (task_id or "").strip().lower()
    if tid:
        goal_ids = [g for g in (mapping.get(tid) or mapping.get(task_id or "") or []) if g]
        if goal_ids:
            return SEGMENT_GOAL_MAPPED
    cat = (category or "").strip().lower()
    if cat and cat in daily_categories:
        return SEGMENT_DAILY_ROUTINE
    return SEGMENT_UNMAPPED
