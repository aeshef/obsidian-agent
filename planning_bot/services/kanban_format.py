"""Kanban task line templates and tag regexes from planning_bot/config/kanban_schema.yaml."""
from __future__ import annotations

import re
from typing import Optional

from planning_bot.core.config import (
    CATEGORIES,
    DEFAULT_CATEGORY,
    DEFAULT_PRIORITY,
    PRIORITIES,
    _kanban_schema,
)
from planning_bot.core.pdmsg import pdmsg


def normalize_category(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw in CATEGORIES:
        return raw
    for cat in CATEGORIES:
        if raw == cat or raw in cat or cat in raw:
            return cat
    return DEFAULT_CATEGORY


def normalize_priority(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw in PRIORITIES:
        return raw
    for pri in PRIORITIES:
        if raw == pri or raw in pri or pri in raw:
            return pri
    return DEFAULT_PRIORITY


def _format_from_schema(key: str, **kwargs: object) -> str:
    tpl = _kanban_schema().get(key)
    if isinstance(tpl, str) and tpl.strip():
        try:
            return tpl.format(**kwargs).strip("\n")
        except (KeyError, ValueError):
            pass
    return ""


def task_meta_line(category: str, priority: str) -> str:
    cat = normalize_category(category)
    pri = normalize_priority(priority)
    line = _format_from_schema("task_meta_template", category=cat, priority=pri)
    if line:
        return line
    line = pdmsg("kanban_task_meta_line", default="", category=cat, priority=pri)
    if line.strip():
        return line
    return pdmsg("auto_743c193451", default="", category=cat, priority=pri)


def task_created_line(created_date: str) -> str:
    line = _format_from_schema("task_created_template", created_date=created_date)
    if line:
        return line
    line = pdmsg("kanban_task_created_line", default="", created_date=created_date)
    if line.strip():
        return line
    return pdmsg("auto_90845dcdf6", default="", created_date=created_date)


def tag_goal_regex() -> re.Pattern[str]:
    raw = _kanban_schema().get("tag_goal_regex")
    if isinstance(raw, str) and raw.strip():
        return re.compile(raw)
    fallback = pdmsg("auto_8d7e383ebe", default="")
    if fallback:
        return re.compile(fallback)
    return re.compile(r"#goal/([^\s#]+)", re.IGNORECASE)


def tag_priority_regex() -> re.Pattern[str]:
    raw = _kanban_schema().get("tag_priority_regex")
    if isinstance(raw, str) and raw.strip():
        return re.compile(raw)
    fallback = pdmsg("auto_a1fb4d656a", default="")
    if fallback:
        return re.compile(fallback)
    alts = "|".join(re.escape(p) for p in PRIORITIES) if PRIORITIES else r"high|medium|low"
    return re.compile(rf"#priority/({alts})", re.IGNORECASE)


def tag_deadline_regex() -> re.Pattern[str]:
    raw = _kanban_schema().get("tag_deadline_regex")
    if isinstance(raw, str) and raw.strip():
        return re.compile(raw)
    fallback = pdmsg("auto_4f6bd2f69f", default="")
    if fallback:
        return re.compile(fallback)
    return re.compile(r"#deadline/(\d{4}-\d{2}-\d{2})")


def tag_created_regex() -> re.Pattern[str]:
    raw = _kanban_schema().get("tag_created_regex")
    if isinstance(raw, str) and raw.strip():
        return re.compile(raw)
    fallback = pdmsg("auto_04f3888a7d", default="")
    if fallback:
        return re.compile(fallback)
    return re.compile(r"Created:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
