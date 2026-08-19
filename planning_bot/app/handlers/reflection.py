"""Weekly reflection and reflection response handlers."""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from planning_bot.app import keyboards
from planning_bot.app.fsm import set_reflection_waiting
from planning_bot.app.handlers import menus
from planning_bot.app.states import ReflectionState
from planning_bot.app.ui import pmsg
from planning_bot.core.config import CALENDAR_JSON_FILE
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.calendar_service import (
    get_week_calendar_summary,
    with_calendar_attendance_note,
)
from shared.agent.platform_config import platform_int
from shared.memory import append_turn
from shared.telegram.messaging import send_long_message

logger = logging.getLogger(__name__)

_REFLECTION_THOUGHTS_HEADER = pdmsg("auto_29e747c3bc")


def _reflection_cfg() -> dict[str, int]:
    return {
        "review_days": platform_int("planning_reflection", "review_days", default=7),
        "review_excerpt_chars": platform_int(
            "planning_reflection", "review_excerpt_chars", default=1500
        ),
        "weekly_logs_limit": platform_int(
            "planning_reflection", "weekly_logs_limit", default=100
        ),
        "previous_reflections_limit": platform_int(
            "planning_reflection", "previous_reflections_limit", default=5
        ),
    }


def _reflection_file_for_sunday(reflection_dir, sunday: datetime) -> "Path":
    from pathlib import Path

    prefix = pdmsg("reflection_file_prefix") or pdmsg("auto_9e853157ef") or "Reflection_"
    return Path(reflection_dir) / f"{prefix}{sunday.strftime('%Y-%m-%d')}.md"


def _sunday_anchor(today: datetime | None = None) -> datetime:
    today = today or datetime.now()
    days_until_sunday = (6 - today.weekday()) % 7
    if days_until_sunday == 0 and today.weekday() == 6:
        return today
    return today + timedelta(days=days_until_sunday)


async def _planning_agent_reply(planning, bot: Bot, chat_id: int, user_message: str, *, context_prefix: str = "") -> None:
    from shared.agent.app import build_app
    from shared.llm import LLMClient
    from shared.telegram.agent_delivery import deliver_agent_answer

    from planning_bot.app.agent_tools import PLANNING_DOMAIN, PlanningAdapter

    question = user_message
    if context_prefix.strip():
        question = f"{context_prefix.strip()}\n\n---\n\n{user_message}"
    app = build_app(LLMClient(), PlanningAdapter(planning))
    await deliver_agent_answer(
        bot,
        chat_id,
        app,
        question,
        domain=PLANNING_DOMAIN,
        reply_markup=keyboards.get_main_keyboard(),
    )


async def start_reflection(self, message: Message, state: FSMContext):
    await message.answer(
        pmsg("reflection_generating"),
        reply_markup=keyboards.get_main_keyboard(),
    )
    try:
        ok, err_msg = self.logger.check_logs_dir_accessible()
        if not ok:
            logger.warning("Weekly review cancelled: %s", err_msg)
            await message.answer(
                pmsg("reflection_logs_unavailable", error=err_msg),
                reply_markup=keyboards.get_main_keyboard(),
            )
            return
        cfg = _reflection_cfg()
        logger.info("Weekly review: logs from %s", self.logger.logs_dir)
        stats = self.kanban.get_statistics(
            completed_this_week_from_logs=self.logger.get_completed_last_days(cfg["review_days"])
        )
        goals = self.goals_manager.get_goals()
        quarterly_focus = self.goals_manager.get_quarterly_focus()
        goals_context = self.goals_manager.get_goals_context()
        previous_reflections = self.reflection_manager.get_previous_reflections_summary(
            limit=cfg["previous_reflections_limit"]
        )
        weekly_logs = self.logger.get_logs_last_days(
            days=cfg["review_days"], limit=cfg["weekly_logs_limit"]
        )
        weekly_moves = self.logger.get_moved_events_last_days(days=cfg["review_days"])
        cal_raw = get_week_calendar_summary(CALENDAR_JSON_FILE, days_back=7, days_ahead=7)
        calendar_events = with_calendar_attendance_note(cal_raw) if cal_raw else None

        review = self.llm.generate_weekly_review(
            stats,
            goals,
            quarterly_focus,
            goals_context,
            previous_reflections,
            weekly_logs,
            weekly_moves,
            calendar_events=calendar_events or None,
        )
        self.reflection_manager.save_weekly_reflection(review)
        await state.set_state(ReflectionState.waiting)
        chat_id = message.chat.id
        append_turn(chat_id, "planning", "assistant", review)
        await send_long_message(
            message.bot,
            chat_id,
            review,
            reply_markup=keyboards.get_main_keyboard(),
        )
        await message.answer(
            pmsg("reflection_thoughts_prompt"),
            reply_markup=keyboards.get_main_keyboard(),
        )
    except Exception as e:
        logger.error("Weekly review generation failed: %s\n%s", e, traceback.format_exc())
        await message.answer(
            pmsg("reflection_error", error=e),
            reply_markup=keyboards.get_main_keyboard(),
        )


async def handle_reflection_response(self, message: Message, state: FSMContext):
    user_message = message.text or ""
    chat_id = message.chat.id
    sunday = _sunday_anchor()
    reflection_file = _reflection_file_for_sunday(self.reflection_manager.reflection_dir, sunday)
    header = _REFLECTION_THOUGHTS_HEADER

    if reflection_file.exists():
        content = reflection_file.read_text(encoding="utf-8")
        if header in content:
            parts = content.split(header, 1)
            if len(parts) > 1:
                existing_thoughts = parts[1].split("---")[0]
                tail = parts[1].split("---", 1)[1] if "---" in parts[1] else ""
                new_content = (
                    parts[0]
                    + header
                    + existing_thoughts
                    + f"\n\n{user_message}\n\n---"
                    + tail
                )
            else:
                new_content = content + f"\n\n{header}\n\n{user_message}\n\n"
        elif "---" in content:
            parts = content.split("---", 1)
            new_content = parts[0] + f"\n\n{header}\n\n{user_message}\n\n---" + parts[1]
        else:
            new_content = content + f"\n\n{header}\n\n{user_message}\n\n"
        reflection_file.write_text(new_content, encoding="utf-8")

    await state.clear()
    try:
        cfg = _reflection_cfg()
        extra = ""
        if reflection_file.exists():
            try:
                review_text = reflection_file.read_text(encoding="utf-8")
                excerpt = review_text[: cfg["review_excerpt_chars"]]
                extra = pdmsg("auto_a05be86f73") + excerpt
            except OSError:
                pass
        await _planning_agent_reply(
            self, message.bot, chat_id, user_message, context_prefix=extra
        )
    except Exception as e:
        logger.error("Reflection LLM reply failed: %s\n%s", e, traceback.format_exc())
        await message.answer(
            pmsg("reflection_thoughts_saved"),
            reply_markup=keyboards.get_main_keyboard(),
        )


async def schedule_weekly_review(self, bot: Bot):
    logger.info("Scheduled weekly review (logs: %s)", self.logger.logs_dir)
    try:
        ok, err_msg = self.logger.check_logs_dir_accessible()
        if not ok:
            logger.warning("Scheduled weekly review cancelled: %s", err_msg)
            if self.chat_id:
                from shared.i18n import msg
                from shared.telegram.push_format import format_push, send_push

                await send_push(
                    bot,
                    self.chat_id,
                    format_push(
                        msg("push", "weekly_review_title"),
                        pmsg("weekly_review_failed", error=err_msg),
                    ),
                    reply_markup=keyboards.get_main_keyboard(),
                )
            return
        stats = self.kanban.get_statistics(
            completed_this_week_from_logs=self.logger.get_completed_this_week()
        )
        goals = self.goals_manager.get_goals()
        quarterly_focus = self.goals_manager.get_quarterly_focus()
        goals_context = self.goals_manager.get_goals_context()
        cfg = _reflection_cfg()
        previous_reflections = self.reflection_manager.get_previous_reflections_summary(
            limit=cfg["previous_reflections_limit"]
        )
        weekly_logs = self.logger.get_weekly_logs(limit=cfg["weekly_logs_limit"])
        weekly_moves = self.logger.get_moved_events_this_week()
        cal_raw = get_week_calendar_summary(CALENDAR_JSON_FILE, days_back=7, days_ahead=7)
        calendar_events = with_calendar_attendance_note(cal_raw) if cal_raw else None

        review = self.llm.generate_weekly_review(
            stats,
            goals,
            quarterly_focus,
            goals_context,
            previous_reflections,
            weekly_logs,
            weekly_moves,
            calendar_events=calendar_events or None,
        )
        self.reflection_manager.save_weekly_reflection(review)
        if self.chat_id:
            append_turn(self.chat_id, "planning", "assistant", review)
            from shared.i18n import msg
            from shared.telegram.push_format import format_push, send_push

            full_text = review + "\n\n" + pmsg("reflection_thoughts_prompt")
            await send_push(
                bot,
                self.chat_id,
                format_push(msg("push", "weekly_review_title"), full_text),
                reply_markup=keyboards.get_main_keyboard(),
            )
            await set_reflection_waiting(
                self.fsm_storage, bot, self.chat_id, self.chat_id, waiting=True
            )
            await menus.send_weekly_goals_no_tasks(self, bot)
        else:
            logger.warning("Chat ID not set, weekly review not sent")
    except Exception as e:
        logger.error("Scheduled weekly review failed: %s\n%s", e, traceback.format_exc())
