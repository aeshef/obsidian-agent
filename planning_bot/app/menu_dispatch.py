"""Planning reply-keyboard dispatch (labels/actions from ui_capabilities menu_actions)."""
from __future__ import annotations

from typing import Awaitable, Callable, List, Tuple

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from planning_bot.app.handlers import tasks
from planning_bot.app.menu_action_handlers import PlanningMenuContext, planning_action_handlers
from planning_bot.app.menu_gates import planning_auto_allowed, planning_submenu_allowed
from planning_bot.core.config import CATEGORIES, KANBAN_COLUMNS, PRIORITIES
from planning_bot.core.pdmsg import pdmsg
from shared.capabilities.menu_actions_config import (
    menu_reply_specs,
    menu_reset_label_keys,
    menu_submenu_specs,
)
from shared.telegram.reply_menu_dispatch import dispatch_label_actions


def _planning_label_actions(
    ctx: PlanningMenuContext,
) -> List[Tuple[str, Callable[[], Awaitable[None]]]]:
    handlers = planning_action_handlers(ctx)
    label_actions: List[Tuple[str, Callable[[], Awaitable[None]]]] = []
    for spec in menu_reply_specs("planning"):
        label_key = str(spec.get("label_key") or "").strip()
        action_id = str(spec.get("action") or "").strip()
        if not label_key or not action_id:
            continue
        if not planning_auto_allowed(label_key):
            continue
        handler = handlers.get(action_id)
        if handler is None:
            continue
        label = pdmsg(label_key)
        if label:
            label_actions.append((label, handler))
    return label_actions


async def dispatch_planning_menu(
    bot,
    message: Message,
    state: FSMContext,
    user_message: str,
) -> bool:
    """Handle planning keyboard / submenu taps. True = consumed."""
    from planning_bot.services.planning_text_triggers import match_planning_text_trigger

    ctx = PlanningMenuContext(bot=bot, message=message, state=state)
    trigger_action = match_planning_text_trigger(user_message)
    if trigger_action:
        handler = planning_action_handlers(ctx).get(trigger_action)
        if handler is not None:
            await handler()
            return True
    low = user_message.lower()
    reset_keys = {
        pdmsg(k).lower()
        for k in menu_reset_label_keys("planning")
        if planning_auto_allowed(k) and pdmsg(k)
    }
    if low in reset_keys:
        from planning_bot.app.handlers.commands import cmd_reset_context

        await cmd_reset_context(bot, message, state)
        return True

    if await dispatch_label_actions(user_message, _planning_label_actions(ctx)):
        return True

    for spec in menu_submenu_specs("planning"):
        kind = str(spec.get("kind") or "").strip()
        if kind == "kanban_column" and user_message in KANBAN_COLUMNS:
            if planning_submenu_allowed("kanban_column"):
                await tasks.show_tasks_by_status(bot, message, column=user_message)
                return True
        elif kind == "category" and user_message.startswith("📋 ") and user_message[2:] in CATEGORIES:
            if planning_submenu_allowed("category"):
                await tasks.show_tasks(bot, message, category=user_message.replace("📋 ", "").strip())
                return True
        elif kind == "priority" and user_message.startswith("📋 ") and user_message[2:] in PRIORITIES:
            if planning_submenu_allowed("priority"):
                await tasks.show_tasks(bot, message, priority=user_message.replace("📋 ", "").strip())
                return True

    return False
