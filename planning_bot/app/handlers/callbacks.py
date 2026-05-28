"""Inline keyboard callback handlers."""
import logging
import traceback

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from planning_bot.app.ui import pmsg
from planning_bot.core.llm import APITimeoutError

logger = logging.getLogger(__name__)


async def button_callback(self, callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    chat_id = callback.from_user.id
    data = callback.data
    if data.startswith("confirm_task"):
        pending_id = data.split(":", 1)[1] if ":" in data else None
        pending_entry = self.pending_tasks.get(pending_id) if pending_id else None
        if not pending_entry or pending_entry.get("chat_id") != chat_id:
            await callback.message.edit_text(pmsg("task_not_found"))
            return
        task = pending_entry["task"]
        try:
            logger.info("Adding task: %s", task["title"][:50])
            task_id = self.kanban.add_task_to_backlog(
                task["title"], task["category"], task["priority"]
            )
            logger.info("Task added with id=%s", task_id)
            self.logger.log_task_created(
                task["title"], task["category"], task["priority"], task_id=task_id
            )
            await callback.message.edit_text(
                pmsg(
                    "task_added_backlog",
                    title=task["title"],
                    category=task["category"],
                    priority=task["priority"],
                )
            )
            if pending_id:
                self.pending_tasks.pop(pending_id, None)
        except APITimeoutError as e:
            logger.error("Timeout while adding task: %s\n%s", e, traceback.format_exc())
            try:
                await callback.message.edit_text(pmsg("timeout_error_short"))
            except Exception as telegram_error:
                logger.error("Telegram edit failed: %s", telegram_error)
        except Exception as e:
            logger.error("Error while adding task: %s\n%s", e, traceback.format_exc())
            error_msg = str(e)
            if (
                "timeout" in error_msg.lower()
                or "timed out" in error_msg.lower()
                or "api" in error_msg.lower()
            ):
                try:
                    await callback.message.edit_text(pmsg("timeout_error_short"))
                except Exception as telegram_error:
                    logger.error("Telegram edit failed: %s", telegram_error)
            else:
                try:
                    await callback.message.edit_text(
                        pmsg("reflection_error", error=error_msg)
                    )
                except Exception as telegram_error:
                    logger.error("Telegram edit failed: %s", telegram_error)
                    try:
                        await callback.bot.send_message(
                            chat_id=callback.from_user.id,
                            text=pmsg("reflection_error", error=error_msg),
                        )
                    except Exception as send_error:
                        logger.error("Telegram send failed: %s", send_error)
    elif data.startswith("edit_task"):
        await callback.message.edit_text(pmsg("edit_task_prompt"))
        pending_id = data.split(":", 1)[1] if ":" in data else None
        if pending_id:
            self.pending_tasks.pop(pending_id, None)
    elif data.startswith("cancel_task"):
        pending_id = data.split(":", 1)[1] if ":" in data else None
        if pending_id:
            self.pending_tasks.pop(pending_id, None)
        await callback.message.edit_text(pmsg("task_cancelled"))
