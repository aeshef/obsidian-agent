"""Planning reply-menu action ids → async callables (specs in ui_capabilities menu_actions)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from planning_bot.app import keyboards
from planning_bot.app.handlers import menus, tasks
from planning_bot.core.pdmsg import pdmsg

ActionFn = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class PlanningMenuContext:
    bot: Any
    message: Message
    state: FSMContext


def planning_action_handlers(ctx: PlanningMenuContext) -> dict[str, ActionFn]:
    bot, message, state = ctx.bot, ctx.message, ctx.state

    async def back_to_main() -> None:
        await message.answer(
            pdmsg("auto_80c02bf46b"),
            reply_markup=keyboards.get_main_keyboard(),
        )

    return {
        "show_tasks_menu": lambda: menus.show_tasks_menu(bot, message),
        "show_categories_menu": lambda: menus.show_categories_menu(bot, message),
        "show_priorities_menu": lambda: menus.show_priorities_menu(bot, message),
        "show_statuses_menu": lambda: menus.show_statuses_menu(bot, message),
        "show_all_tasks": lambda: tasks.show_tasks(bot, message),
        "back_to_main": back_to_main,
        "show_routines_stats": lambda: menus.show_routines_statistics(bot, message),
        "routines_recommendations": lambda: bot.get_routines_recommendations(message),
        "show_pending_routines": lambda: menus.show_pending_routines(bot, message),
        "start_reflection": lambda: bot.start_reflection(message, state),
    }


PLANNING_ACTION_IDS = frozenset(
    {
        "show_tasks_menu",
        "show_categories_menu",
        "show_priorities_menu",
        "show_statuses_menu",
        "show_all_tasks",
        "back_to_main",
        "show_routines_stats",
        "routines_recommendations",
        "show_pending_routines",
        "start_reflection",
    }
)
