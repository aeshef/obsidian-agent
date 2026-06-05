"""Domain dispatch from host: mode switch, user bootstrap."""
from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from shared.i18n import msg
from shared.telegram.host.constants import DOMAIN_FINANCE, DOMAIN_IDS, UI_MODE_AUTO
from shared.telegram.host.keyboards import keyboard_for_mode


async def ensure_finance_user(message: Message) -> None:
    from sqlalchemy import select

    from bot.db import AsyncSessionLocal
    from bot.models import Account, User

    tg_id = message.from_user.id
    chat_id = message.chat.id
    wallet_name = msg("finance", "default_wallet_name")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            user = User(telegram_id=tg_id, chat_id=chat_id)
            session.add(user)
            await session.flush()
        else:
            user.chat_id = chat_id
        exists = (
            await session.execute(select(Account.id).where(Account.user_id == user.id).limit(1))
        ).first()
        if exists is None:
            session.add(
                Account(user_id=user.id, name=wallet_name, type="wallet", currency=user.base_currency)
            )
        await session.commit()


async def switch_mode(message: Message, state: FSMContext, mode: str) -> None:
    if mode != UI_MODE_AUTO:
        from shared.capabilities.profile import (
            MODULE_FINANCE,
            MODULE_KNOWLEDGE,
            MODULE_PLANNING,
            get_capabilities,
        )

        prof = get_capabilities()
        allowed = {
            DOMAIN_FINANCE: MODULE_FINANCE,
            "planning": MODULE_PLANNING,
            "knowledge": MODULE_KNOWLEDGE,
        }
        mod = allowed.get(mode)
        if mod and not prof.module(mod):
            mode = UI_MODE_AUTO
    await state.update_data(ui_mode=mode, fixed_domain=mode if mode != "auto" else None)
    if mode == DOMAIN_FINANCE:
        await ensure_finance_user(message)
    mode_keys = {
        DOMAIN_FINANCE: "switch_finance",
        "planning": "switch_planning",
        "knowledge": "switch_knowledge",
    }
    text = msg("host", mode_keys.get(mode, "switch_auto"))
    uid = message.chat.id if message.chat else None
    kb = keyboard_for_mode(mode if mode != UI_MODE_AUTO else "auto", user_id=uid)
    await message.answer(text, reply_markup=kb)
