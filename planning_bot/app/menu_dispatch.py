"""Planning reply-keyboard dispatch (labels from pdmsg / kanban schema)."""
from __future__ import annotations

from typing import Awaitable, Callable, List, Tuple

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from planning_bot.app import keyboards
from planning_bot.app.handlers import menus, tasks
from planning_bot.core.config import CATEGORIES, KANBAN_COLUMNS, PRIORITIES
from planning_bot.core.pdmsg import pdmsg

_RESET_KEYS: Tuple[str, ...] = (
    "auto_322fab4a99",
    "auto_27c8e8e900",
    "auto_f0bc732b56",
)


async def dispatch_planning_menu(
    bot,
    message: Message,
    state: FSMContext,
    user_message: str,
) -> bool:
    """Handle planning keyboard / submenu taps. True = consumed."""
    low = user_message.lower()
    if low in {pdmsg(k).lower() for k in _RESET_KEYS}:
        from planning_bot.app.handlers.commands import cmd_reset_context

        await cmd_reset_context(bot, message, state)
        return True

    label_actions: List[Tuple[str, Callable[[], Awaitable[None]]]] = [
        ("auto_ca15d9d2aa", lambda: menus.show_tasks_menu(bot, message)),
        ("auto_edc1040220", lambda: menus.show_categories_menu(bot, message)),
        ("auto_8771b735cb", lambda: menus.show_priorities_menu(bot, message)),
        ("auto_a0b7b44b3f", lambda: menus.show_statuses_menu(bot, message)),
        ("auto_e9917f3011", lambda: tasks.show_tasks(bot, message)),
        (
            "auto_dc232d1607",
            lambda: message.answer(
                pdmsg("auto_80c02bf46b"),
                reply_markup=keyboards.get_main_keyboard(),
            ),
        ),
        ("auto_f317ab8f35", lambda: menus.show_routines_statistics(bot, message)),
        ("auto_b6b32200b7", lambda: bot.get_routines_recommendations(message)),
        ("auto_7a4a4c1791", lambda: menus.show_pending_routines(bot, message)),
        ("auto_f895d3042c", lambda: bot.start_reflection(message, state)),
    ]

    for key, action in label_actions:
        if user_message == pdmsg(key):
            await action()
            return True

    if user_message in KANBAN_COLUMNS:
        await tasks.show_tasks_by_status(bot, message, column=user_message)
        return True

    if user_message.startswith("📋 ") and user_message[2:] in CATEGORIES:
        await tasks.show_tasks(bot, message, category=user_message.replace("📋 ", "").strip())
        return True

    if user_message.startswith("📋 ") and user_message[2:] in PRIORITIES:
        await tasks.show_tasks(bot, message, priority=user_message.replace("📋 ", "").strip())
        return True

    return False
