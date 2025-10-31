from decimal import Decimal
from uuid import uuid4

from typing import Optional, List
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.ui import fmsg
from shared.domain_messages import dmsg
from shared.ui import common

from ..db import AsyncSessionLocal
from ..models import User, Account, Transaction


router = Router()


class TransferState(StatesGroup):
    from_acc = State()
    to_acc = State()
    amount = State()
    fee = State()
    confirm = State()
    wizard_message_id = State()


def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=common("cancel_button"), callback_data="tr:cancel")]])


async def _set_msg(state: FSMContext, message: types.Message) -> None:
    await state.update_data(wizard_message_id=message.message_id)


async def _edit(message: types.Message, state: FSMContext, text: str, kb: Optional[InlineKeyboardMarkup] = None) -> None:
    data = await state.get_data()
    mid = data.get("wizard_message_id")
    if mid:
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=mid, text=text, reply_markup=kb)
            return
        except Exception as e:
            import logging
            log = logging.getLogger("finance.transfers")
            log.warning("Failed to edit message %s: %s", mid, e)
    m = await message.answer(text, reply_markup=kb)
    await _set_msg(state, m)


def _accounts_kb(accounts: List[Account], prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=a.name, callback_data=f"{prefix}:{a.id}")] for a in accounts]
    rows.append([InlineKeyboardButton(text=common("cancel_button"), callback_data="tr:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "action:transfer")
async def start_transfer(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await state.clear()
    await state.set_state(TransferState.from_acc)

    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().unique().all()
        # Transfers between cards/wallets (not broker)
        accounts = [a for a in accounts if a.type in ("card", "wallet") or not a.is_external_balance]
    try:
        await _edit(message, state, fmsg("transfer_select_from"), _accounts_kb(accounts, "tr:from"))
    except Exception:
        # Fallback: send new message if edit fails
        m = await message.answer(fmsg("transfer_select_from"), reply_markup=_accounts_kb(accounts, "tr:from"))
        await _set_msg(state, m)
    await callback.answer()


@router.callback_query(TransferState.from_acc, F.data.startswith("tr:from:"))
async def set_from(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    from_id = int(callback.data.split(":")[-1])
    await state.update_data(from_id=from_id)

    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().unique().all()
        accounts = [a for a in accounts if (a.type in ("card", "wallet") or not a.is_external_balance) and a.id != from_id]
    await state.set_state(TransferState.to_acc)
    await _edit(message, state, fmsg("transfer_select_to"), _accounts_kb(accounts, "tr:to"))
    await callback.answer()


@router.callback_query(TransferState.to_acc, F.data.startswith("tr:to:"))
async def set_to(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    to_id = int(callback.data.split(":")[-1])
    await state.update_data(to_id=to_id)
    await state.set_state(TransferState.amount)
    await _edit(message, state, fmsg("transfer_amount_prompt"), kb_cancel())
    await callback.answer()


@router.message(TransferState.amount)
async def set_amount(message: types.Message, state: FSMContext) -> None:
    try:
        amount = Decimal(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except Exception:
        await _edit(message, state, fmsg("transfer_invalid_amount"), kb_cancel())
        return
    await state.update_data(amount=str(amount))
    try:
        await message.delete()
    except Exception as e:
        import logging
        log = logging.getLogger("finance.transfers")
        log.debug("Failed to delete user message: %s", e)
    await state.set_state(TransferState.fee)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fmsg("transfer_fee_zero"), callback_data="tr:fee:0")],
        [InlineKeyboardButton(text=fmsg("transfer_fee_custom"), callback_data="tr:fee:custom")],
        [InlineKeyboardButton(text=common("cancel_button"), callback_data="tr:cancel")],
    ])
    await _edit(message, state, fmsg("transfer_fee_prompt"), kb)


@router.callback_query(TransferState.fee, F.data == "tr:fee:0")
async def fee_zero(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await state.update_data(fee="0")
    await _show_confirm(message, state)
    await callback.answer()


@router.callback_query(TransferState.fee, F.data == "tr:fee:custom")
async def fee_custom(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await _edit(message, state, fmsg("invest_fee_amount"), kb_cancel())
    await callback.answer()


@router.message(TransferState.fee)
async def fee_amount(message: types.Message, state: FSMContext) -> None:
    try:
        fee = Decimal(message.text.replace(",", "."))
        if fee < 0:
            raise ValueError
    except Exception:
        await _edit(message, state, fmsg("transfer_invalid_fee"), kb_cancel())
        return
    await state.update_data(fee=str(fee))
    try:
        await message.delete()
    except Exception as e:
        import logging
        log = logging.getLogger("finance.transfers")
        log.debug("Failed to delete user message: %s", e)
    await _show_confirm(message, state)


async def _show_confirm(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        from_acc = (await session.execute(select(Account).where(Account.id == int(data["from_id"])))).scalar_one()
        to_acc = (await session.execute(select(Account).where(Account.id == int(data["to_id"])))).scalar_one()
    amount = Decimal(data["amount"]).quantize(Decimal("0.01"))
    fee = Decimal(data.get("fee", "0")).quantize(Decimal("0.01"))
    text = fmsg(
        "transfer_confirm",
        from_name=from_acc.name,
        from_currency=from_acc.currency,
        to_name=to_acc.name,
        to_currency=to_acc.currency,
        amount=amount,
        fee=fee,
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fmsg("wizard_confirm_btn"), callback_data="tr:confirm")],
        [InlineKeyboardButton(text=common("cancel_button"), callback_data="tr:cancel")],
    ])
    await state.set_state(TransferState.confirm)
    await _edit(message, state, text, kb)


@router.callback_query(TransferState.confirm, F.data == "tr:confirm")
async def do_transfer(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    data = await state.get_data()
    from_id = int(data["from_id"]) 
    to_id = int(data["to_id"]) 
    amount = Decimal(data["amount"]) 
    fee = Decimal(data.get("fee", "0"))

    async with AsyncSessionLocal() as session:
        from_acc = (await session.execute(select(Account).where(Account.id == from_id))).scalar_one()
        to_acc = (await session.execute(select(Account).where(Account.id == to_id))).scalar_one()
        if from_acc.currency != to_acc.currency:
            await callback.answer(fmsg("transfer_no_fx"), show_alert=True)
            return
        # expense from source (amount + fee)
        transfer_cat = dmsg("finance", "transfer_category")
        session.add(Transaction(
            user_id=from_acc.user_id,
            account_id=from_acc.id,
            type="expense",
            amount=amount + fee,
            currency=from_acc.currency,
            category=transfer_cat,
            description=dmsg("finance", "transfer_out_description", account=to_acc.name),
        ))
        session.add(Transaction(
            user_id=to_acc.user_id,
            account_id=to_acc.id,
            type="income",
            amount=amount,
            currency=to_acc.currency,
            category=transfer_cat,
            description=dmsg("finance", "transfer_in_description", account=from_acc.name),
        ))
        await session.commit()

    await state.clear()
    await message.edit_text(fmsg("transfer_done"))
    await callback.answer()


@router.callback_query(F.data == "tr:cancel")
async def cancel_transfer(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(common("cancelled"))
    await callback.answer()
