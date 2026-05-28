"""Task listing, creation, and statistics handlers."""
import logging
import re
import traceback
import uuid
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from planning_bot.app import keyboards
from planning_bot.app.ui import pmsg
from planning_bot.core.config import (
    CALENDAR_JSON_FILE,
    category_emoji,
    priority_emoji,
)
from planning_bot.core.llm import APITimeoutError
from planning_bot.services.calendar_service import get_upcoming_events_text, with_calendar_attendance_note

logger = logging.getLogger(__name__)


async def process_task_message(self, message: Message, user_message: str):
    chat_id = message.chat.id
    await message.answer(pmsg("analyzing_task"), reply_markup=keyboards.get_main_keyboard())
    try:
        recent_tasks = [t["title"] for t in self.kanban.get_backlog_tasks()[:5]]
        goals = self.goals_manager.get_goals()[:5]
        upcoming_raw = get_upcoming_events_text(CALENDAR_JSON_FILE, hours_ahead=48)
        upcoming_events = with_calendar_attendance_note(upcoming_raw) if upcoming_raw else ""
        context_data = {
            "recent_tasks": recent_tasks,
            "goals": goals,
            **({"upcoming_events": upcoming_events} if upcoming_events else {}),
        }
        parsed = self.llm.parse_task(user_message, context_data)
        pending_id = uuid.uuid4().hex[:10]
        self.pending_tasks[pending_id] = {"chat_id": chat_id, "task": parsed}
        confirmation_text = pmsg(
            "task_confirm",
            title=parsed["title"],
            category=parsed["category"],
            priority=parsed["priority"],
        )
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=pmsg("confirm_yes"), callback_data=f"confirm_task:{pending_id}"),
                    InlineKeyboardButton(text=pmsg("confirm_edit"), callback_data=f"edit_task:{pending_id}"),
                ],
                [InlineKeyboardButton(text=pmsg("confirm_cancel"), callback_data=f"cancel_task:{pending_id}")],
            ]
        )
        await message.answer(confirmation_text, reply_markup=reply_markup, parse_mode="Markdown")
    except APITimeoutError as e:
        logger.error("Timeout while processing task: %s\n%s", e, traceback.format_exc())
        await message.answer(pmsg("timeout_error"), reply_markup=keyboards.get_main_keyboard())
    except Exception as e:
        logger.error("Error while processing task: %s\n%s", e, traceback.format_exc())
        error_msg = str(e)
        if (
            "timeout" in error_msg.lower()
            or "timed out" in error_msg.lower()
            or "api" in error_msg.lower()
        ):
            await message.answer(pmsg("timeout_error_short"), reply_markup=keyboards.get_main_keyboard())
        else:
            await message.answer(pmsg("task_process_error"), reply_markup=keyboards.get_main_keyboard())


async def show_tasks_by_status(self, message: Message, column: str):
    try:
        self.kanban.load()
        self.kanban.load_state()
        all_tasks = self.kanban.get_tasks(exclude_today=False, exclude_blocked=False)
        tasks = [t for t in all_tasks if t.get("column") == column]
        tasks_per_message = 15
        total = len(tasks)
        header = pmsg("column_header", column=column, total=total)
        if not tasks:
            await message.answer(
                pmsg("no_tasks_in_column", column=column),
                reply_markup=keyboards.get_statuses_keyboard(),
            )
            return
        for i in range(0, total, tasks_per_message):
            batch = tasks[i : i + tasks_per_message]
            if i == 0:
                text = header
            else:
                end = min(i + tasks_per_message, total)
                text = pmsg("column_batch_header", column=column, start=i + 1, end=end, total=total)
            for j, task in enumerate(batch, 1):
                title = (task.get("title") or "").strip().replace("\n", " ").replace("\r", "")
                title = re.sub(r"\s+", " ", title)
                text += f"{i + j}. {title}\n"
            await message.answer(text.rstrip(), reply_markup=keyboards.get_statuses_keyboard())
    except Exception as e:
        logger.error("Error in show_tasks_by_status: %s\n%s", e, traceback.format_exc())
        await message.answer(pmsg("load_tasks_error"), reply_markup=keyboards.get_statuses_keyboard())


async def show_tasks(
    self,
    message: Message,
    category: Optional[str] = None,
    priority: Optional[str] = None,
):
    try:
        logger.info("show_tasks category=%s priority=%s", category, priority)
        self.kanban.load()
        all_tasks = self.kanban.get_backlog_tasks(exclude_today=False)
        if category:
            all_tasks = [t for t in all_tasks if t.get("category") == category]
        if priority:
            all_tasks = [t for t in all_tasks if t.get("priority") == priority]
        if not all_tasks:
            filter_text = ""
            if category:
                filter_text += pmsg("filter_by_category", category=category)
            if priority:
                filter_text += pmsg("filter_by_priority", priority=priority)
            await message.answer(
                pmsg("no_active_tasks", filter=filter_text),
                reply_markup=keyboards.get_tasks_filter_keyboard(),
            )
            return
        filter_text = ""
        if category:
            filter_text += f" {category_emoji(category)} {category}"
        if priority:
            pe = priority_emoji(priority)
            filter_text += f" + {pe} {priority}" if filter_text else f" {pe} {priority}"
        header = (
            pmsg("tasks_header", filter=filter_text)
            if filter_text
            else pmsg("tasks_header_plain")
        )
        tasks_per_message = 10
        total_tasks = len(all_tasks)
        for message_num in range(0, total_tasks, tasks_per_message):
            batch = all_tasks[message_num : message_num + tasks_per_message]
            if message_num == 0:
                text = header
            else:
                end = min(message_num + tasks_per_message, total_tasks)
                text = pmsg(
                    "tasks_continuation",
                    start=message_num + 1,
                    end=end,
                    total=total_tasks,
                )
            for i, task in enumerate(batch, 1):
                task_num = message_num + i
                pe = priority_emoji(task.get("priority", ""))
                ce = category_emoji(task.get("category", ""))
                task_title = re.sub(
                    r"\s+",
                    " ",
                    task.get("title", "").strip().replace("\n", " ").replace("\r", ""),
                )
                text += f"{task_num}. {pe} {ce} {task_title}\n"
            if message_num + tasks_per_message >= total_tasks and (category or priority):
                text += pmsg("filter_change_hint")
            await message.answer(
                text.rstrip(),
                parse_mode="Markdown",
                reply_markup=keyboards.get_tasks_filter_keyboard(),
            )
    except Exception as e:
        logger.error("Error in show_tasks: %s\n%s", e, traceback.format_exc())
        await message.answer(pmsg("load_tasks_error"), reply_markup=keyboards.get_tasks_filter_keyboard())


async def show_statistics(self, message: Message):
    try:
        stats = self.kanban.get_statistics()
        stats["completed"] = self.logger.count_completed_tasks_this_week()
        text = pmsg("stats_header")
        text += pmsg("stats_completed", count=stats.get("completed", 0))
        text += pmsg("stats_active", count=stats.get("backlog_size", 0))
        by_category = stats.get("by_category", {})
        if by_category:
            text += pmsg("stats_by_category")
            for cat, count in list(by_category.items())[:5]:
                text += pmsg("stats_category_line", category=cat, count=count)
        try:
            await message.answer(
                text, parse_mode="Markdown", reply_markup=keyboards.get_main_keyboard()
            )
        except Exception as send_err:
            logger.warning("Statistics Markdown send failed, plain fallback: %s", send_err)
            from shared.telegram_utils import strip_telegram_markdown

            await message.answer(
                strip_telegram_markdown(text),
                reply_markup=keyboards.get_main_keyboard(),
            )
    except Exception as e:
        logger.error("Error in show_statistics: %s\n%s", e, traceback.format_exc())
        await message.answer(pmsg("load_tasks_error"), reply_markup=keyboards.get_main_keyboard())
