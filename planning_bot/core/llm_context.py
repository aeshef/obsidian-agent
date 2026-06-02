"""Build LLM prompt context strings (text from domain_messages.yaml)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from planning_bot.core.config import (
    BACKLOG_COLUMN,
    BLOCKED_COLUMN,
    DEFAULT_CATEGORY,
    DEFAULT_PRIORITY,
    IN_WORK_COLUMN,
    WAITING_DATE_COLUMN,
)
from planning_bot.core.pdmsg import pdmsg

def month_name_ru(month: int) -> str:
    return pdmsg(f"llm_month_{month:02d}")


def weekday_name_ru(weekday: int) -> str:
    return pdmsg(f"llm_weekday_{weekday}")


def weekday_name_en_to_ru(day_en: str) -> str:
    key = day_en.lower()[:3]
    return pdmsg(f"llm_weekday_en_{key}", default=day_en)


def mac_iphone_recommendations_block(parts: List[str]) -> str:
    return pdmsg("llm_mac_iphone_block") + "\n\n".join(parts)


def parse_task_defaults() -> tuple[str, str]:
    return DEFAULT_CATEGORY, DEFAULT_PRIORITY


def weekly_review_completed_header() -> str:
    return pdmsg("llm_weekly_completed_header")


def weekly_review_completed_more(count: int) -> str:
    return pdmsg("llm_weekly_completed_more", count=count)


def weekly_review_stats_text(
    *,
    week_start_str: str,
    week_end_str: str,
    weekday_str: str,
    formed_at_str: str,
    time_str: str,
    backlog_only: int,
    in_waiting_date: int,
    in_postponed: int,
    in_work: int,
    in_blocked: int,
    total_active: int,
    completed: int,
    num_moves: int,
    by_category: object,
    by_priority: object,
    completed_titles_block: str,
) -> str:
    return pdmsg(
        "llm_weekly_review_stats",
        week_start=week_start_str,
        week_end=week_end_str,
        weekday=weekday_str,
        formed_at=formed_at_str,
        time=time_str,
        col_backlog=BACKLOG_COLUMN,
        col_waiting=WAITING_DATE_COLUMN,
        col_postponed=pdmsg("llm_col_postponed"),
        col_in_work=IN_WORK_COLUMN,
        col_blocked=BLOCKED_COLUMN,
        backlog_only=backlog_only,
        in_waiting_date=in_waiting_date,
        in_postponed=in_postponed,
        in_work=in_work,
        in_blocked=in_blocked,
        total_active=total_active,
        completed=completed,
        num_moves=num_moves,
        by_category=by_category,
        by_priority=by_priority,
        completed_titles_block=completed_titles_block,
    )


def weekly_review_goals_text(goals: List[str]) -> str:
    return pdmsg("llm_weekly_goals_header") + "\n".join(f"- {g}" for g in goals)


def weekly_review_focus_text(focus: List[str]) -> str:
    return pdmsg("llm_weekly_focus_header") + "\n".join(f"- {g}" for g in focus)


def weekly_review_calendar_prefix() -> str:
    return pdmsg("llm_weekly_calendar_prefix")


def weekly_review_moves_header() -> str:
    return pdmsg("llm_weekly_moves_header")


def weekly_review_moves_more(extra: int, total: int) -> str:
    return pdmsg("llm_weekly_moves_more", extra=extra, total=total)


def weekly_review_goals_context_block(goals_context: str) -> str:
    return pdmsg("llm_weekly_goals_context", body=goals_context)


def weekly_review_reflections_block(previous: str) -> str:
    return pdmsg("llm_weekly_reflections", body=previous[:1000])


def weekly_review_logs_block(weekly_logs: str) -> str:
    return pdmsg("llm_weekly_action_logs", body=weekly_logs)


def weekly_review_user_prompt(context_text: str) -> str:
    return pdmsg("llm_weekly_user_prompt", context=context_text)


def recommendations_date_ru(day: int, month: int, year: int) -> str:
    return pdmsg("llm_date_ru", day=day, month=month_name_ru(month), year=year)


def recommendations_is_weekend(weekday: int) -> str:
    return pdmsg("llm_weekend_yes") if weekday >= 5 else pdmsg("llm_weekend_no")


def recommendations_task_line_meta(category: str, priority: str) -> str:
    return pdmsg("llm_task_meta", category=category, priority=priority)


def recommendations_task_created(date: str) -> str:
    return pdmsg("llm_task_created", date=date)


def recommendations_task_deadline(deadline: str) -> str:
    return pdmsg("llm_task_deadline", deadline=deadline)


def recommendations_task_history(history: str) -> str:
    return pdmsg("llm_task_history", history=history)


def recommendations_task_goals(goals_text: str) -> str:
    return pdmsg("llm_task_goals", goals=goals_text)


def recommendations_stats_summary(total: int, in_work: int, backlog: int) -> str:
    return pdmsg(
        "llm_recommendations_stats",
        total=total,
        in_work=in_work,
        backlog=backlog,
    )


def recommendations_context_body(
    stats_summary: str,
    tasks_text: str,
    weekly_stats: object,
    goals_joined: str,
) -> str:
    return pdmsg(
        "llm_recommendations_context",
        stats=stats_summary,
        tasks=tasks_text,
        weekly_stats=weekly_stats,
        goals=goals_joined,
    )


def recommendations_goals_context_block(goals_context: str) -> str:
    return pdmsg("llm_recommendations_goals_context", body=goals_context)


def recommendations_identity_block(identity_summary: str) -> str:
    return pdmsg("llm_recommendations_identity", body=identity_summary[:500])


def recommendations_logs_block(weekly_logs: str) -> str:
    return pdmsg("llm_recommendations_logs", body=weekly_logs)


def recommendations_calendar_block(calendar_context: str) -> str:
    return pdmsg("llm_recommendations_calendar", body=calendar_context)


def recommendations_anchor_hint(
    current_date_ru: str, current_date_iso: str, current_time_msk: str
) -> str:
    return pdmsg(
        "llm_recommendations_anchor",
        date_ru=current_date_ru,
        date_iso=current_date_iso,
        time_msk=current_time_msk,
    )


def recommendations_user_message(anchor_hint: str, context: str) -> str:
    return pdmsg("llm_recommendations_user", anchor=anchor_hint, context=context)


def goals_mapping_header() -> str:
    return pdmsg("llm_goals_mapping_header")


def goals_mapping_line(
    goal_id: str,
    goal_text: str,
    goal_category: str,
    goal_quarter: str,
    goal_priority: str,
) -> str:
    return pdmsg(
        "llm_goals_mapping_line",
        goal_id=goal_id,
        goal_text=goal_text,
        category=goal_category,
        quarter=goal_quarter,
        priority=goal_priority,
    )


def goals_mapping_user_message(task_title: str, task_category: str) -> str:
    return pdmsg("llm_goals_mapping_user", title=task_title, category=task_category)


def parse_task_recent_header() -> str:
    return pdmsg("llm_parse_recent_header")


def parse_task_goals_header() -> str:
    return pdmsg("llm_parse_goals_header")
