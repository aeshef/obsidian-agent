from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from sqlalchemy import select

from bot.filters import BadgeText, MenuText
from bot.menu_labels import fin_menu
from bot.ui import fmsg
from shared.ui import common

from ..config_loader import get_badge_config, is_badge_enabled
from ..db import AsyncSessionLocal
from ..models import Account, User

router = Router()
menu_callbacks_router = Router(name="finance_menu_callbacks")


def _badge_label() -> str:
    if is_badge_enabled():
        return (get_badge_config().get("ui") or {}).get("menu_button") or fin_menu("badge")
    return fin_menu("badge")


def _badge_visible() -> bool:
    from shared.capabilities.ui_bindings import message_allowed

    return is_badge_enabled() and message_allowed("finance", "menu", "badge")


def _badge_inline_row() -> list[InlineKeyboardButton]:
    if _badge_visible():
        return [InlineKeyboardButton(text=_badge_label(), callback_data="action:badge")]
    return []


def _badge_reply_row() -> list[KeyboardButton]:
    if _badge_visible():
        return [KeyboardButton(text=_badge_label())]
    return []


def main_menu_inline() -> InlineKeyboardMarkup:
    from shared.capabilities.finance_ui import invest_menu_visible

    rows: list[list[InlineKeyboardButton]] = []
    badge = _badge_inline_row()
    if badge:
        rows.append(badge)
    invest_rows: list[list[InlineKeyboardButton]] = []
    from shared.capabilities.ui_bindings import message_allowed

    invest_label = fin_menu("invest")
    if invest_menu_visible() and message_allowed("finance", "menu", "invest") and invest_label:
        invest_rows.append([InlineKeyboardButton(text=invest_label, callback_data="action:invest")])
    rows.extend(
        invest_rows
        + [
            [
                InlineKeyboardButton(text=fin_menu("balance"), callback_data="action:balance"),
                InlineKeyboardButton(text=fin_menu("last_ops"), callback_data="action:last"),
            ],
            [InlineKeyboardButton(text=fin_menu("plan"), callback_data="action:plan_list")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_reply() -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []
    badge = _badge_reply_row()
    if badge:
        keyboard.append(badge)
    keyboard.append(
        [
            KeyboardButton(text=fin_menu("balance")),
            KeyboardButton(text=fin_menu("last_ops")),
        ]
    )
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder=fmsg("placeholder_main"),
    )


@menu_callbacks_router.callback_query(F.data == "action:menu")
async def back_to_menu(callback: types.CallbackQuery) -> None:
    text = fmsg("start_greeting")
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_inline())
    except Exception as e:
        import logging

        log = logging.getLogger("finance.start")
        log.warning("Failed to edit message: %s", e)
        await callback.message.answer(text, reply_markup=main_menu_inline())
    await callback.answer()


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    tg_id = message.from_user.id
    chat_id = message.chat.id

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            user = User(telegram_id=tg_id, chat_id=chat_id)
            session.add(user)
            await session.flush()
        else:
            user.chat_id = chat_id

        exists_row = (
            await session.execute(select(Account.id).where(Account.user_id == user.id).limit(1))
        ).first()
        if exists_row is None:
            session.add(
                Account(
                    user_id=user.id,
                    name=fmsg("default_wallet_name"),
                    type="wallet",
                    currency=user.base_currency,
                )
            )
        await session.commit()

    await message.answer(fmsg("start_greeting"), reply_markup=main_menu_reply())


class _FakeCallback:
    def __init__(self, msg: types.Message, data: str) -> None:
        self.message = msg
        self.from_user = msg.from_user
        self.data = data

    async def answer(self) -> None:
        pass


@router.message(MenuText("add_expense"))
async def handle_add_expense_button(message: types.Message, state) -> None:
    from .transactions import add_expense_cb

    await add_expense_cb(_FakeCallback(message, "action:add_expense"), state)


@router.message(BadgeText())
async def handle_badge_button(message: types.Message, state) -> None:
    from .badge import badge_menu_cb

    await badge_menu_cb(_FakeCallback(message, "action:badge"), state)


@router.message(MenuText("add_income"))
async def handle_add_income_button(message: types.Message, state) -> None:
    from .transactions import add_income_cb

    await add_income_cb(_FakeCallback(message, "action:add_income"), state)


@router.message(MenuText("transfer"))
async def handle_transfer_button(message: types.Message, state) -> None:
    import logging

    log = logging.getLogger("finance.start")
    try:
        from .transfers import start_transfer

        await start_transfer(_FakeCallback(message, "action:transfer"), state)
    except Exception as e:
        log.error("transfer handler: %s", e, exc_info=True)
        await message.answer(common("error", error=e))


@router.message(MenuText("debts"))
async def handle_debts_button(message: types.Message, state) -> None:
    import logging

    log = logging.getLogger("finance.start")
    try:
        from .debts import debts_menu

        await debts_menu(_FakeCallback(message, "action:debts"), state)
    except Exception as e:
        log.error("debts handler: %s", e, exc_info=True)
        await message.answer(common("error", error=e))


@router.message(MenuText("invest"))
async def handle_investments_button(message: types.Message, state) -> None:
    import logging

    log = logging.getLogger("finance.start")
    try:
        from .investments import invest_menu

        await invest_menu(_FakeCallback(message, "action:invest"))
    except Exception as e:
        log.error("invest handler: %s", e, exc_info=True)
        await message.answer(common("error", error=e))


@router.message(MenuText("balance"))
async def handle_balance_button(message: types.Message, state) -> None:
    import logging

    log = logging.getLogger("finance.start")
    try:
        from .transactions import _render_balance

        text, kb = await _render_balance(message.from_user.id)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        log.error("balance handler: %s", e, exc_info=True)
        await message.answer(common("error", error=e))


@router.message(MenuText("last_ops"))
async def handle_last_button(message: types.Message, state) -> None:
    from .recent import last_default

    await last_default(_FakeCallback(message, "action:last"))


@router.message(MenuText("summary"))
async def handle_summary_button(message: types.Message, state) -> None:
    import logging

    log = logging.getLogger("finance.start")
    try:
        from .summary import cmd_summary

        await cmd_summary(_FakeCallback(message, "action:summary"))
    except Exception as e:
        log.error("summary handler: %s", e, exc_info=True)
        await message.answer(common("error", error=e))


@router.message(MenuText("plan"))
async def handle_plan_button(message: types.Message, state) -> None:
    from .planning import list_plans

    await list_plans(_FakeCallback(message, "action:plan_list"))


@router.message(MenuText("sync"))
async def handle_sync_button(message: types.Message, state) -> None:
    from .integrations import sync_menu

    await sync_menu(_FakeCallback(message, "action:sync_menu"))
