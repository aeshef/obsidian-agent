"""Tests for goals-mapping task segments."""
from __future__ import annotations

from shared.goals.task_segment import (
    SEGMENT_DAILY_ROUTINE,
    SEGMENT_GOAL_MAPPED,
    SEGMENT_UNMAPPED,
    classify_task_goal_segment,
    flow_daily_categories,
)


def test_classify_goal_mapped():
    mapping = {"abc": ["g1"]}
    assert (
        classify_task_goal_segment("abc", "карьера", mapping, frozenset({"дом"}))
        == SEGMENT_GOAL_MAPPED
    )


def test_classify_daily_routine_without_mapping():
    mapping: dict[str, list[str]] = {}
    assert (
        classify_task_goal_segment("x1", "дом", mapping, frozenset({"дом"}))
        == SEGMENT_DAILY_ROUTINE
    )


def test_classify_unmapped():
    mapping: dict[str, list[str]] = {}
    assert (
        classify_task_goal_segment("x1", "карьера", mapping, frozenset({"дом"}))
        == SEGMENT_UNMAPPED
    )


def test_flow_daily_categories_from_schema():
    schema = {"flow_metrics": {"daily_routine_categories": ["Home", "дом"]}}
    cats = flow_daily_categories(schema)
    assert "home" in cats
    assert "дом" in cats
