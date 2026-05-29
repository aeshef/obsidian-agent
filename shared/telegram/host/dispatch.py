"""Domain dispatch from host: mode switch, user bootstrap."""
from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from shared.i18n import msg
from shared.telegram.host.constants import DOMAIN_FINANCE, DOMAIN_IDS, UI_MODE_AUTO
from shared.telegram.host.keyboards import (
    auto_keyboard,
    finance_keyboard,
    knowledge_keyboard,
    planning_keyboard,
)


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
        text = msg("host", "switch_finance")
        kb = finance_keyboard()
    elif mode == "planning":
        text = msg("host", "switch_planning")
        kb = planning_keyboard()
    elif mode == "knowledge":
        text = msg("host", "switch_knowledge")
        from knowledge_bot.app.state import is_bulk_ingest

        uid = message.from_user.id if message.from_user else None
        kb = knowledge_keyboard(bulk_active=is_bulk_ingest(uid) if uid else False)
    else:
        text = msg("host", "switch_auto")
        kb = auto_keyboard()
    await message.answer(text, reply_markup=kb)
