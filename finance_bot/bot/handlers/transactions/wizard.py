"""Manual add-expense/income wizard."""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.db import AsyncSessionLocal
from bot.ui import fmsg
from shared.ui import common
from bot.models import User, Account, Transaction
from bot.services.categories import load_categories
from bot.services.transactions import parse_occurred_at
from bot.handlers.transactions.nlu import process_transactions
from bot.handlers.transactions.states import AddTxnState

log = logging.getLogger("finance.transactions.wizard")
router = Router()

def inline_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=common("cancel_button"), callback_data="wizard:cancel")]]
    )


async def _set_wizard_message(state: FSMContext, message: types.Message) -> None:
    await state.update_data(wizard_message_id=message.message_id)


async def _edit_wizard(message: types.Message, state: FSMContext, text: str, kb: Optional[InlineKeyboardMarkup] = None) -> None:
    data = await state.get_data()
    msg_id = data.get("wizard_message_id")
    if msg_id:
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=text, reply_markup=kb)
            return
        except Exception as e:
            log.warning("Failed to edit wizard message %s: %s", msg_id, e)
    m = await message.answer(text, reply_markup=kb)
    await _set_wizard_message(state, m)


def _categories_keyboard(kind: str) -> InlineKeyboardMarkup:
    cats = load_categories(kind)
    rows = []
    row: List[InlineKeyboardButton] = []
    for c in cats:
        row.append(InlineKeyboardButton(text=c, callback_data=f"wizard:cat:{c}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=fmsg("wizard_cat_text_btn"), callback_data="wizard:cat_text")])
    rows.append([
        InlineKeyboardButton(text=fmsg("sync_back_button"), callback_data="action:menu"),
        InlineKeyboardButton(text=common("cancel_button"), callback_data="wizard:cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _main_menu_inline() -> InlineKeyboardMarkup:
    """Menu button row (used from start.py)."""
    from .start import main_menu_inline
    return main_menu_inline()


@router.callback_query(F.data == "action:add_expense")
async def add_expense_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await state.set_state(AddTxnState.type)
    await state.update_data(type="expense")
    await state.set_state(AddTxnState.amount)
    await _edit_wizard(message, state, fmsg("wizard_expense_amount"), inline_cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "action:add_income")
async def add_income_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await state.set_state(AddTxnState.type)
    await state.update_data(type="income")
    await state.set_state(AddTxnState.amount)
    await _edit_wizard(message, state, fmsg("wizard_income_amount"), inline_cancel_kb())
    await callback.answer()


# Voice in wizard removed (AddTxnState.amount, F.voice); handled in @router.message(F.voice)


@router.message(AddTxnState.amount, F.text)
async def add_amount(message: types.Message, state: FSMContext) -> None:
    """All wizard text goes through LLM without keyword gates."""
    text = message.text.strip()
    log.info("Wizard text %r — clearing state and routing to LLM", text)
    await state.clear()
    await process_transactions(text, message, state)


@router.callback_query(AddTxnState.category, F.data.startswith("wizard:cat:"))
async def choose_category_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    cat = callback.data.split(":", 2)[-1]
    await state.update_data(category=cat)

    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        accounts = [a for a in accounts if not a.is_external_balance]
        if not accounts:
            acc = Account(user_id=user.id, name=fmsg("default_wallet_name"), type="wallet", currency=user.base_currency)
            session.add(acc)
            await session.commit()
            accounts = [acc]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=a.name, callback_data=f"wizard:acc:{a.id}")]
            for a in accounts
        ]
        + [[InlineKeyboardButton(text=common("cancel_button"), callback_data="wizard:cancel")]]
    )
    await state.set_state(AddTxnState.account)
    await _edit_wizard(message, state, fmsg("wizard_select_account"), kb)
    await callback.answer()


@router.callback_query(AddTxnState.category, F.data == "wizard:cat_text")
async def choose_category_text_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await _edit_wizard(message, state, fmsg("wizard_category_text"), inline_cancel_kb())
    await callback.answer()


# Voice in wizard category state removed — main voice handler only


@router.message(AddTxnState.category, F.text)
async def add_category(message: types.Message, state: FSMContext) -> None:
    await state.update_data(category=message.text.strip())
    try:
        await message.delete()
    except Exception as e:
        log.debug("Failed to delete user message: %s", e)

    async with AsyncSessionLocal() as session:
        tg_id = message.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        accounts = [a for a in accounts if not a.is_external_balance]
        if not accounts:
            acc = Account(user_id=user.id, name=fmsg("default_wallet_name"), type="wallet", currency=user.base_currency)
            session.add(acc)
            await session.commit()
            accounts = [acc]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=a.name, callback_data=f"wizard:acc:{a.id}")]
            for a in accounts
        ]
        + [[InlineKeyboardButton(text=common("cancel_button"), callback_data="wizard:cancel")]]
    )
    await state.set_state(AddTxnState.account)
    await _edit_wizard(message, state, fmsg("wizard_select_account"), kb)


@router.callback_query(AddTxnState.account, F.data.startswith("wizard:acc:"))
async def add_account_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle account selection and show confirmation preview."""
    message = callback.message
    acc_id_str = callback.data.split(":")[-1]
    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        account = (
            await session.execute(select(Account).where(Account.user_id == user.id, Account.id == int(acc_id_str)))
        ).scalar_one_or_none()
        if account is None or account.is_external_balance:
            await callback.answer(fmsg("wizard_account_forbidden"), show_alert=True)
            return

        await state.update_data(account_id=account.id)

        data = await state.get_data()
        amount = Decimal(data["amount"])
        txn_type = data["type"]
        category = data.get("category", fmsg("wizard_no_category"))

        emoji = "➖" if txn_type == "expense" else "➕"
        text = fmsg("wizard_confirm_header", emoji=emoji)
        text += fmsg("wizard_confirm_type", txn_type=txn_type)
        text += fmsg("wizard_confirm_amount", amount=amount, currency=account.currency)
        text += fmsg("wizard_confirm_category", category=category)
        text += fmsg("wizard_confirm_account", account=account.name)

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=fmsg("wizard_confirm_btn"), callback_data="wizard:confirm")],
                [InlineKeyboardButton(text=common("cancel_button"), callback_data="wizard:cancel")],
            ]
        )

        await state.set_state(AddTxnState.confirm)
        await _edit_wizard(message, state, text, kb)
        await callback.answer()


@router.callback_query(AddTxnState.confirm, F.data == "wizard:confirm")
async def confirm_transaction_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Persist transaction after user confirmation."""
    message = callback.message
    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()

        data = await state.get_data()
        account_id = data.get("account_id")
        if not account_id:
            await callback.answer(fmsg("wizard_account_missing"), show_alert=True)
            await state.clear()
            return

        account = (
            await session.execute(select(Account).where(Account.user_id == user.id, Account.id == account_id))
        ).scalar_one_or_none()

        if not account:
            await callback.answer(fmsg("wizard_account_not_found"), show_alert=True)
            await state.clear()
            return

        txn = Transaction(
            user_id=user.id,
            account_id=account.id,
            type=data["type"],
            amount=Decimal(data["amount"]),
            currency=account.currency,
            category=data.get("category"),
        )
        session.add(txn)
        await session.commit()

    await state.clear()
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text=fmsg("confirm_recorded"),
        reply_markup=_main_menu_inline(),
    )
    await callback.answer()


@router.callback_query(F.data == "wizard:cancel")
async def wizard_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(common("cancelled"))
    await callback.answer()
