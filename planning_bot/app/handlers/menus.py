"""Menu navigation, routines, goals progress, and scheduled alerts."""
from __future__ import annotations

import logging
import traceback
from collections import defaultdict
from datetime import datetime as dt
from typing import Dict, List

from aiogram import Bot
from aiogram.types import Message

from planning_bot.app import keyboards
from planning_bot.app.ui import pmsg
from planning_bot.core.config import (
    DONE_COLUMN,
    IN_WORK_COLUMN,
    WAITING_DATE_COLUMN,
    priority_emoji,
)
from planning_bot.services.routines_analyzer import (
    format_statistics_text,
    get_pending_tasks,
    get_statistics as get_routines_statistics,
    should_send_evening_reminder,
    should_send_morning_reminder,
)

logger = logging.getLogger(__name__)
from shared.telegram.ui_send import answer_card


async def show_tasks_menu(self, message: Message):
    await answer_card(message, pmsg("tasks_menu_title"),
        reply_markup=keyboards.get_tasks_filter_keyboard(),)


async def show_categories_menu(self, message: Message):
    await answer_card(message, pmsg("categories_menu_title"),
        reply_markup=keyboards.get_categories_keyboard(),)


async def show_priorities_menu(self, message: Message):
    await answer_card(message, pmsg("priorities_menu_title"),
        reply_markup=keyboards.get_priorities_keyboard(),)


async def show_statuses_menu(self, message: Message):
    await answer_card(message, pmsg("statuses_menu_title"),
        reply_markup=keyboards.get_statuses_keyboard(),)


async def show_routines_menu(self, message: Message):
    await answer_card(message, pmsg("routines_menu_title"),
        reply_markup=keyboards.get_routines_keyboard(),)


async def show_routines_statistics(self, message: Message):
    try:
        stats = get_routines_statistics(days=30)
        text = format_statistics_text(stats)
        await answer_card(message, text, reply_markup=keyboards.get_routines_keyboard()
        )
    except Exception as e:
        logger.error("Routines stats failed: %s\n%s", e, traceback.format_exc())
        await answer_card(message, pmsg("routines_stats_error"),
            reply_markup=keyboards.get_routines_keyboard(),
        )


async def show_pending_routines(self, message: Message):
    try:
        pending = get_pending_tasks()
        text = pmsg("pending_routines_header")
        if pending["morning"]:
            text += pmsg("morning_section") + "".join(f"• {t}\n" for t in pending["morning"]) + "\n"
        else:
            text += pmsg("morning_all_done")
        if pending["day"]:
            text += pmsg("day_section") + "".join(f"• {t}\n" for t in pending["day"]) + "\n"
        else:
            text += pmsg("day_all_done")
        if pending["evening"]:
            text += pmsg("evening_section") + "".join(f"• {t}\n" for t in pending["evening"])
        else:
            text += pmsg("evening_all_done")
        await answer_card(message, text, reply_markup=keyboards.get_routines_keyboard())
    except Exception as e:
        logger.error("Pending routines failed: %s", e)
        await answer_card(message, pmsg("pending_routines_error"),
            reply_markup=keyboards.get_routines_keyboard(),
        )


async def show_goals_progress(self, message: Message):
    try:
        current_quarter = self.goals_mapper.get_current_quarter()
        progress_text = self.goals_analyzer.format_progress_text(current_quarter)
        alerts_text = self.goals_analyzer.format_alerts_text(current_quarter)
        await message.answer(
            progress_text + "\n" + alerts_text,
            reply_markup=keyboards.get_main_keyboard(),
        )
    except Exception as e:
        logger.error("Goals progress failed: %s\n%s", e, traceback.format_exc())
        await answer_card(message, pmsg("goals_progress_error"),
            reply_markup=keyboards.get_main_keyboard(),
        )


def _plain_bullet_lines(items: list[str], *, limit: int = 5) -> str:
    lines = [f"• {item}" for item in items[:limit]]
    if len(items) > limit:
        lines.append(pmsg("more_tasks_suffix", count=len(items) - limit).strip())
    return "\n".join(lines)


async def send_morning_brief(self, bot: Bot):
    """One morning push: routines + stuck (+ optional deadlines/goals) in one style."""
    from shared.i18n import msg, msgf
    from shared.telegram.push_format import format_push_sections
    from shared.telegram.push_policy import in_quiet_hours, morning_brief_includes

    try:
        if not self.chat_id:
            logger.warning("Chat ID not set, skip morning brief")
            return
        if in_quiet_hours():
            logger.info("Skip morning brief: quiet hours")
            return

        sections: list[tuple[str, str]] = []

        if morning_brief_includes("routines", default=True):
            pending = get_pending_tasks()
            morning = pending.get("morning") or []
            if morning:
                sections.append(
                    (
                        msg("push", "section_routines"),
                        _plain_bullet_lines(morning),
                    )
                )

        if morning_brief_includes("stuck", default=True):
            days = _stuck_task_days()
            stuck = get_stuck_tasks(self, stuck_days=days)
            if stuck:
                body = "\n".join(
                    f"• {t['title'][:60]} · {t.get('column', '')} · {t['days_stuck']}d"
                    for t in stuck[:6]
                )
                sections.append((msg("push", "section_stuck"), body))

        if morning_brief_includes("deadlines", default=True):
            missed = self.kanban.get_tasks_with_missed_deadlines()
            upcoming = self.kanban.get_tasks_with_deadlines(days_ahead=7)
            if missed or upcoming:
                lines: list[str] = []
                for task in (missed or [])[:4]:
                    lines.append(
                        msgf(
                            "push",
                            "deadline_overdue_item",
                            title=task.get("title", "")[:50],
                        )
                    )
                for task in (upcoming or [])[:4]:
                    lines.append(
                        msgf(
                            "push",
                            "deadline_upcoming_item",
                            title=task.get("title", "")[:50],
                            deadline=task.get("deadline", ""),
                        )
                    )
                if lines:
                    sections.append((msg("push", "section_deadlines"), "\n".join(lines)))

        if morning_brief_includes("goals", default=True):
            current_quarter = self.goals_mapper.get_current_quarter()
            problematic = self.goals_analyzer.get_problematic_goals(current_quarter)
            if problematic:
                body = "\n".join(
                    f"• {p.get('goal', {}).get('text', '?')[:60]}"
                    for p in problematic[:5]
                )
                sections.append((msg("push", "section_goals"), body))

        text = format_push_sections(
            msg("push", "morning_brief_title"),
            sections,
            footer=msg("push", "morning_brief_footer"),
        )
        if not text:
            logger.info("Morning brief empty — skip send")
            return
        from shared.telegram.push_format import send_push
        await send_push(bot, self.chat_id, text)
        logger.info("Sent morning brief sections=%s", len(sections))
    except Exception as e:
        logger.error("Morning brief failed: %s", e)


async def send_morning_routine_reminder(self, bot: Bot):
    try:
        if not should_send_morning_reminder() or not self.chat_id:
            if not self.chat_id:
                logger.warning("Chat ID not set, skip morning routine reminder")
            return
        from shared.telegram.push_policy import in_quiet_hours

        if in_quiet_hours():
            logger.info("Skip morning routine reminder: quiet hours")
            return
        pending = get_pending_tasks()
        if not pending["morning"]:
            return
        from shared.i18n import msg
        from shared.telegram.push_format import format_push

        body = _plain_bullet_lines(pending["morning"])
        text = format_push(msg("push", "section_routines"), body)
        from shared.telegram.push_format import send_push
        await send_push(bot, self.chat_id, text)
        logger.info("Sent morning routine reminder")
    except Exception as e:
        logger.error("Morning routine reminder failed: %s", e)


async def send_daily_checkin_prompt(self, bot: Bot):
    try:
        if not self.chat_id:
            logger.warning("Chat ID not set, skip daily check-in prompt")
            return
        from planning_bot.app.handlers.daily_checkin import send_daily_checkin_prompt

        if await send_daily_checkin_prompt(bot, self.chat_id):
            logger.info("Sent daily check-in prompt")
        else:
            logger.info("Daily check-in prompt skipped (already closed or snoozed)")
    except Exception as e:
        logger.error("Daily check-in prompt failed: %s", e)


async def send_evening_routine_reminder(self, bot: Bot):
    try:
        if not should_send_evening_reminder() or not self.chat_id:
            if not self.chat_id:
                logger.warning("Chat ID not set, skip evening routine reminder")
            return
        from shared.telegram.push_policy import in_quiet_hours

        if in_quiet_hours():
            logger.info("Skip evening routine reminder: quiet hours")
            return
        pending = get_pending_tasks()
        if not pending["evening"]:
            return
        from shared.i18n import msg
        from shared.telegram.push_format import format_push

        body = _plain_bullet_lines(pending["evening"])
        text = format_push(msg("push", "section_evening_routines"), body)
        from shared.telegram.push_format import send_push
        await send_push(bot, self.chat_id, text)
        logger.info("Sent evening routine reminder")
    except Exception as e:
        logger.error("Evening routine reminder failed: %s", e)


async def send_weekly_goals_no_tasks(self, bot: Bot):
    try:
        if not self.chat_id:
            return
        current_quarter = self.goals_mapper.get_current_quarter()
        problematic = self.goals_analyzer.get_problematic_goals(current_quarter)
        goals_no_tasks = [p for p in problematic if "no_tasks" in p.get("issues", [])]
        if not goals_no_tasks:
            return
        goal_lines = "\n".join(f"• {p.get('goal', {}).get('text', '?')}" for p in goals_no_tasks)
        from shared.telegram.push_format import format_push, send_push

        from shared.i18n import msg

        text = format_push(
            msg("push", "section_goals"),
            pmsg("weekly_goals_no_tasks", quarter=current_quarter, goals=goal_lines),
        )
        await send_push(bot, self.chat_id, text, reply_markup=keyboards.get_main_keyboard())
        logger.info(
            "Weekly goals-without-tasks message sent for %s (%s goals)",
            current_quarter,
            len(goals_no_tasks),
        )
    except Exception as e:
        logger.error("Weekly goals-without-tasks message failed: %s", e)


async def send_goals_alerts(self, bot: Bot):
    logger.info("Running daily goals alerts")
    try:
        if not self.chat_id:
            logger.warning("Chat ID not set, goals alerts skipped")
            return
        current_quarter = self.goals_mapper.get_current_quarter()
        problematic = self.goals_analyzer.get_problematic_goals(current_quarter)
        if problematic:
            alerts_text = self.goals_analyzer.format_alerts_text(current_quarter)
            from shared.i18n import msg
            from shared.telegram.push_format import format_push, send_push

            text = format_push(
                msg("push", "section_goals"),
                pmsg("goals_alerts_header", quarter=current_quarter, alerts=alerts_text),
            )
            await send_push(bot, self.chat_id, text)
            logger.info("Sent goals alerts for %s goals", len(problematic))
    except Exception as e:
        logger.error("Goals alerts failed: %s", e)


async def send_deadlines_alerts(self, bot: Bot):
    logger.info("Running daily deadline alerts")
    try:
        if not self.chat_id:
            logger.warning("Chat ID not set, deadline alerts skipped")
            return
        missed = self.kanban.get_tasks_with_missed_deadlines()
        upcoming = self.kanban.get_tasks_with_deadlines(days_ahead=7)
        if not missed and not upcoming:
            return
        parts: list[str] = []
        if missed:
            parts.append(pmsg("missed_deadlines_header"))
            for task in missed:
                days_over = task.get("days_overdue", 0)
                pri = priority_emoji(task.get("priority", ""))
                column_emoji = "🔄" if task.get("column") == IN_WORK_COLUMN else "📋"
                parts.append(f"{pri} {column_emoji} {task.get('title', '')[:60]}\n")
                parts.append(
                    pmsg(
                        "deadline_overdue_line",
                        deadline=task.get("deadline"),
                        days=days_over,
                    )
                )
            parts.append("\n")
        if upcoming:
            by_days: dict[int, list] = defaultdict(list)
            for task in upcoming:
                by_days[task.get("days_until_deadline", 0)].append(task)
            if 1 in by_days:
                parts.append(pmsg("reminder_one_day", count=len(by_days[1])))
            parts.append(pmsg("upcoming_deadlines_header"))
            for days in sorted(by_days.keys()):
                if days == 0:
                    parts.append(pmsg("deadline_today"))
                elif days == 1:
                    parts.append(pmsg("deadline_tomorrow"))
                elif days <= 3:
                    parts.append(pmsg("deadline_in_days", days=days))
                else:
                    parts.append(pmsg("deadline_in_days_many", days=days))
                for task in by_days[days]:
                    pri = priority_emoji(task.get("priority", ""))
                    column_emoji = "🔄" if task.get("column") == IN_WORK_COLUMN else "📋"
                    parts.append(f"{pri} {column_emoji} {task.get('title', '')[:60]}\n")
                    parts.append(pmsg("deadline_line", deadline=task.get("deadline")))
        from shared.i18n import msg
        from shared.telegram.push_format import format_push, send_push

        text = format_push(msg("push", "section_deadlines"), "".join(parts).strip())
        await send_push(bot, self.chat_id, text)
        logger.info(
            "Deadline alerts sent: missed=%s upcoming=%s",
            len(missed),
            len(upcoming),
        )
    except Exception as e:
        logger.error("Deadline alerts failed: %s", e)


def _stuck_task_days() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int("planning_alerts", "stuck_task_days", default=14)


def get_stuck_tasks(self, stuck_days: int | None = None) -> List[Dict]:
    if stuck_days is None:
        stuck_days = _stuck_task_days()
    all_tasks = self.kanban.get_tasks(exclude_today=False, exclude_blocked=True)
    today = dt.now().date()
    stuck: list[Dict] = []
    for task in all_tasks:
        column = task.get("column") or ""
        if column in (DONE_COLUMN, WAITING_DATE_COLUMN):
            continue
        title = task.get("title", "")
        if not title:
            continue
        last_activity_date = None
        history = self.logger.get_task_history(task_title=title, task_id=task.get("task_id"))
        if history:
            try:
                last_activity_date = dt.strptime(history[-1]["timestamp"][:10], "%Y-%m-%d").date()
            except ValueError:
                pass
        if last_activity_date is None:
            created = task.get("created_date")
            if created:
                try:
                    last_activity_date = dt.strptime(created, "%Y-%m-%d").date()
                except ValueError:
                    pass
        if last_activity_date is None:
            continue
        days_inactive = (today - last_activity_date).days
        if days_inactive >= stuck_days:
            stuck.append({"title": title, "column": column, "days_stuck": days_inactive})
    stuck.sort(key=lambda x: x["days_stuck"], reverse=True)
    return stuck


async def send_stuck_alerts(self, bot: Bot):
    logger.info("Running daily stuck-task alerts")
    try:
        if not self.chat_id:
            logger.warning("Chat ID not set, stuck alerts skipped")
            return
        from shared.telegram.push_policy import in_quiet_hours

        if in_quiet_hours():
            logger.info("Skip stuck alerts: quiet hours")
            return
        days = _stuck_task_days()
        stuck = get_stuck_tasks(self, stuck_days=days)
        if not stuck:
            return
        from shared.i18n import msg
        from shared.telegram.push_format import format_push

        body = "\n".join(
            f"• {t['title'][:60]} · {t.get('column', '')} · {t['days_stuck']}d"
            for t in stuck[:8]
        )
        text = format_push(msg("push", "section_stuck"), body)
        from shared.telegram.push_format import send_push
        await send_push(bot, self.chat_id, text)
        logger.info("Stuck-task alerts sent: %s tasks", len(stuck))
    except Exception as e:
        logger.error("Stuck alerts failed: %s", e)
