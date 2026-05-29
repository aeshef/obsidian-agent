"""FSM helpers for planning_bot."""
from __future__ import annotations

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from planning_bot.app.states import ReflectionState


def user_fsm(storage: BaseStorage, bot: Bot, chat_id: int, user_id: int) -> FSMContext:
    return FSMContext(
        storage=storage,
        key=StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id),
    )


async def is_reflection_waiting(storage: BaseStorage, bot: Bot, chat_id: int, user_id: int) -> bool:
    state = await user_fsm(storage, bot, chat_id, user_id).get_state()
    return state == ReflectionState.waiting.state


async def set_reflection_waiting(
    storage: BaseStorage, bot: Bot, chat_id: int, user_id: int, *, waiting: bool
) -> None:
    ctx = user_fsm(storage, bot, chat_id, user_id)
    if waiting:
        await ctx.set_state(ReflectionState.waiting)
    else:
        await ctx.clear()
