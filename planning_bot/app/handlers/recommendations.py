"""LLM recommendations for tasks and routines."""
from __future__ import annotations

import logging
import traceback

from aiogram.types import Message

from planning_bot.app import keyboards
from planning_bot.app.ui import pmsg
from planning_bot.core.config import BACKLOG_COLUMN, CALENDAR_JSON_FILE, IN_WORK_COLUMN
from planning_bot.core.pdmsg import pdmsg, pdmsg_nl
from planning_bot.core.settings import load_prompt
from planning_bot.services.calendar_service import (
    get_upcoming_events_text,
    get_week_calendar_summary,
    with_calendar_attendance_note,
)
from planning_bot.services.routines_analyzer import (
    format_statistics_text,
    get_current_time_msk,
    get_pending_tasks,
    get_problematic_tasks,
    get_statistics as get_routines_statistics,
)

logger = logging.getLogger(__name__)


async def get_recommendations(self, message: Message):
    await message.answer(
        pmsg("recommendations_analyzing"),
        reply_markup=keyboards.get_main_keyboard(),
    )
    try:
        try:
            current_state = self.kanban_monitor.load_state()
            logger.info("kanban_state.json synced: %s tasks", len(current_state))
            in_work_count = sum(1 for v in current_state.values() if v == IN_WORK_COLUMN)
            if in_work_count > 0:
                logger.info("Tasks in work per state file: %s", in_work_count)
            else:
                logger.warning("No in-work tasks in kanban_state.json")
        except Exception as e:
            logger.error("kanban_state.json sync failed: %s", e, exc_info=True)

        self.kanban.load_state()
        tasks = self.kanban.get_active_tasks(exclude_blocked=True)
        logger.info("Active tasks for recommendations: %s", len(tasks))
        goals = self.goals_manager.get_goals()
        stats = self.kanban.get_statistics()
        stats["completed"] = self.logger.count_completed_tasks_this_week()
        goals_context = self.goals_manager.get_goals_context()
        identity = self.reflection_manager.get_previous_reflections_summary(limit=3)
        weekly_logs = self.logger.get_weekly_logs(limit=100)
        tasks_history = self.logger.get_tasks_movement_history(tasks)
        tasks_mapping = {}
        for task in tasks:
            task_id = task.get("task_id")
            if not task_id:
                continue
            goal_ids = self.goals_mapper.mapping.get(task_id, [])
            if not goal_ids:
                continue
            related_goals = []
            for goal_id in goal_ids:
                goal = self.goals_mapper.goals.get(goal_id)
                if goal:
                    related_goals.append({
                        "text": goal.get("text", ""),
                        "priority": goal.get("priority", ""),
                        "quarter": goal.get("quarter", ""),
                    })
            tasks_mapping[task_id] = related_goals

        cal_parts = []
        upcoming = get_upcoming_events_text(CALENDAR_JSON_FILE, hours_ahead=72)
        if upcoming:
            cal_parts.append(upcoming)
        week_cal = get_week_calendar_summary(
            CALENDAR_JSON_FILE, days_back=0, days_ahead=7
        )
        if week_cal:
            cal_parts.append(week_cal)
        calendar_context = None
        if cal_parts:
            calendar_context = with_calendar_attendance_note("\n\n".join(cal_parts))

        recommendations = self.llm.generate_recommendations(
            tasks,
            goals,
            stats,
            goals_context,
            identity,
            weekly_logs,
            tasks_mapping,
            tasks_history,
            calendar_context=calendar_context,
        )
        await message.answer(recommendations, reply_markup=keyboards.get_main_keyboard())
    except Exception as e:
        logger.error(
            "Recommendations generation failed: %s\n%s", e, traceback.format_exc()
        )
        await message.answer(
            pmsg("reflection_error", error=str(e)),
            reply_markup=keyboards.get_main_keyboard(),
        )


async def get_routines_recommendations(self, message: Message):
    from shared.capabilities.planning_gates import planning_routines_enabled
    from shared.i18n import msg

    if not planning_routines_enabled():
        await message.answer(
            msg("finance", "connector_unavailable"),
            reply_markup=keyboards.get_main_keyboard(),
        )
        return
    try:
        await message.answer(
            pmsg("routines_recommendations_analyzing"),
            reply_markup=keyboards.get_routines_keyboard(),
        )
        stats = get_routines_statistics(days=30)
        problematic = get_problematic_tasks(days=30, min_failures=2)
        pending = get_pending_tasks()
        stats_text = format_statistics_text(stats)

        if problematic:
            problematic_text = "\n".join(
                pdmsg(
                    "routines_problematic_line",
                    task=task["task"],
                    section=task["section"],
                    fail_rate=task["fail_rate"],
                )
                for task in problematic[:5]
            )
        else:
            problematic_text = pdmsg("routines_no_problematic")

        uncompleted_parts: list[str] = []
        if pending["morning"]:
            uncompleted_parts.append(
                pdmsg_nl(
                    "routines_uncompleted_morning",
                    tasks=", ".join(pending["morning"][:5]),
                )
            )
        if pending["day"]:
            uncompleted_parts.append(
                pdmsg_nl(
                    "routines_uncompleted_day",
                    tasks=", ".join(pending["day"][:5]),
                )
            )
        if pending["evening"]:
            uncompleted_parts.append(
                pdmsg_nl(
                    "routines_uncompleted_evening",
                    tasks=", ".join(pending["evening"][:5]),
                )
            )
        uncompleted_text = "".join(uncompleted_parts) if uncompleted_parts else pdmsg("routines_all_done")

        now_msk = get_current_time_msk()
        from planning_bot.core import llm_context as lc

        prompt_template = load_prompt(self.config_path, "routines_recommendations")
        system_prompt = prompt_template.format(
            current_time_msk=now_msk.strftime("%H:%M"),
            day_of_week=lc.weekday_name_ru(now_msk.weekday()),
            is_weekend=lc.recommendations_is_weekend(now_msk.weekday()),
            statistics_text=stats_text,
            problematic_tasks_text=problematic_text,
            uncompleted_tasks_text=uncompleted_text,
            patterns_text=pdmsg(
                "routines_patterns",
                days=stats["days_analyzed"],
                total_days=stats["total_days"],
            ),
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": pdmsg("routines_recommendations_user")},
        ]
        recommendations = self.llm.chat(messages, temperature=0.7)
        await message.answer(
            pmsg("routines_recommendations_header", recommendations=recommendations),
            parse_mode="Markdown",
            reply_markup=keyboards.get_routines_keyboard(),
        )
    except Exception as e:
        logger.error(
            "Routines recommendations failed: %s\n%s", e, traceback.format_exc()
        )
        await message.answer(
            pmsg("routines_recommendations_error"),
            reply_markup=keyboards.get_routines_keyboard(),
        )
