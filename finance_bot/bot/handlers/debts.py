from decimal import Decimal
import re

from typing import Optional, Tuple
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
from .transactions import _parse_occurred_at


router = Router()


class DebtState(StatesGroup):
    mode = State()  # receivable|payable|settle_recv|settle_pay
    name = State()
    amount = State()
    select_acc = State()
    wizard_message_id = State()


def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=common("cancel_button"), callback_data="debt:cancel"),
                InlineKeyboardButton(text=common("menu_home"), callback_data="action:menu"),
            ]
        ]
    )


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
            log = logging.getLogger("finance.debts")
            log.warning("Failed to edit message %s: %s", mid, e)
    m = await message.answer(text, reply_markup=kb)
    await _set_msg(state, m)


def _menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=fmsg("inline_debt_recv"), callback_data="debt:recv")],
        [InlineKeyboardButton(text=fmsg("inline_debt_pay"), callback_data="debt:pay")],
        [InlineKeyboardButton(text=fmsg("inline_debt_settle_recv"), callback_data="debt:settle_recv")],
        [InlineKeyboardButton(text=fmsg("inline_debt_settle_pay"), callback_data="debt:settle_pay")],
        [
            InlineKeyboardButton(text=common("menu_home"), callback_data="action:menu"),
            InlineKeyboardButton(text=common("cancel_button"), callback_data="debt:cancel"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "action:debts")
async def debts_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await _edit(callback.message, state, fmsg("debts_menu"), _menu_kb())
    except Exception:
        # edit failed — send a new message
        m = await callback.message.answer(fmsg("debts_menu"), reply_markup=_menu_kb())
        await _set_msg(state, m)
    await callback.answer()


@router.callback_query(F.data.in_(["debt:recv", "debt:pay", "debt:settle_recv", "debt:settle_pay"]))
async def debts_route(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = callback.data.split(":")[1]  # recv, pay, settle_recv, settle_pay
    message = callback.message
    await state.update_data(mode=data)
    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        kind_type = "debt_receivable" if data in ("recv", "settle_recv") else "debt_payable"
        accs = (
            await session.execute(
                select(Account).where(Account.user_id == user.id, Account.type == kind_type)
            )
        ).scalars().all()
    rows = [[InlineKeyboardButton(text=a.name.split(":",1)[1] if ":" in a.name else a.name, callback_data=f"debt:cp:{a.name}")]
            for a in accs]
    rows.append([InlineKeyboardButton(text=fmsg("inline_debt_new_counterparty"), callback_data="debt:new")])
    rows.append(
        [
            InlineKeyboardButton(text=common("back"), callback_data="action:debts"),
            InlineKeyboardButton(text=common("menu_home"), callback_data="action:menu"),
        ]
    )
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await state.set_state(DebtState.name)
    await _edit(message, state, fmsg("debts_select_counterparty"), kb)
    await callback.answer()


@router.message(DebtState.name)
async def debt_set_name(message: types.Message, state: FSMContext) -> None:
    name = message.text.strip()
    await state.update_data(counterparty=name)
    try:
        await message.delete()
    except Exception as e:
        import logging
        log = logging.getLogger("finance.debts")
        log.debug("Failed to delete user message: %s", e)
    await state.set_state(DebtState.amount)
    await _edit(message, state, fmsg("debts_amount_prompt"), kb_cancel())


@router.callback_query(DebtState.name, F.data.startswith("debt:cp:"))
async def debt_choose_existing(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    cp = callback.data.split(":", 2)[-1]
    cp_short = cp.split(":", 1)[-1] if ":" in cp else cp
    await state.update_data(counterparty=cp_short)
    await state.set_state(DebtState.amount)
    await _edit(message, state, fmsg("debts_amount_for", counterparty=cp_short), kb_cancel())
    await callback.answer()


@router.callback_query(DebtState.name, F.data == "debt:new")
async def debt_new_cp(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await _edit(message, state, fmsg("debts_counterparty_name_prompt"), kb_cancel())
    await callback.answer()


async def _upsert_debt_account(session, user_id: int, mode: str, name: str, currency: str) -> Account:
    acc_type = "receivable" if mode in ("recv", "settle_recv") else "liability_payable"
    acc_name = f"{acc_type}:{name}"
    acc = (
        await session.execute(select(Account).where(Account.user_id == user_id, Account.name == acc_name))
    ).scalar_one_or_none()
    if acc is None:
        acc = Account(
            user_id=user_id,
            name=acc_name,
            type=acc_type,
            currency=currency,
            is_external_balance=True,
            external_balance=Decimal("0"),
        )
        session.add(acc)
        await session.flush()
    return acc


def _parse_amount_and_currency(text: str) -> Tuple[Optional[Decimal], Optional[str]]:
    """Parse amount strings like '135', '135.5', '135 GBP', '100,50 EUR'."""
    text = text.strip()
    # number with optional trailing currency
    m = re.match(r"^([\d\s.,]+)\s*([A-Za-z]{3})?$", text)
    if not m:
        return None, None
    num_str = m.group(1).replace(",", ".").replace(" ", "")
    try:
        amount = Decimal(num_str)
        if amount <= 0:
            return None, None
    except Exception:
        return None, None
    currency = (m.group(2) or "").upper() or None
    if currency and len(currency) == 3:
        return amount, currency
    return amount, None


@router.message(DebtState.amount)
async def debt_set_amount(message: types.Message, state: FSMContext) -> None:
    amount, currency_override = _parse_amount_and_currency(message.text)
    if amount is None:
        await _edit(message, state, fmsg("debts_invalid_amount"), kb_cancel())
        return

    data = await state.get_data()
    mode = data.get("mode")

    async with AsyncSessionLocal() as session:
        tg_id = message.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        if currency_override:
            currency = currency_override
        else:
            first_acc = (
                await session.execute(
                    select(Account)
                    .where(Account.user_id == user.id, Account.is_external_balance == False)
                    .order_by(Account.id.asc())
                    .limit(1)
                )
            ).scalars().first()
            currency = first_acc.currency if first_acc else "RUB"

        # store amount/currency; record debt or ask for account
        await state.update_data(amount=str(amount), currency=currency, counterparty=data.get("counterparty"))

        # receivable: ask which account funded the loan
        if mode == "recv":
            accs = (
                await session.execute(
                    select(Account)
                    .where(Account.user_id == user.id, Account.is_external_balance == False)
                    .order_by(Account.id.asc())
                )
            ).scalars().all()
            if not accs:
                await state.clear()
                await message.answer(fmsg("debts_no_accounts_out"))
                return
            rows = [
                [InlineKeyboardButton(text=f"{a.name} ({a.currency})", callback_data=f"debt:from:{a.id}")]
                for a in accs
            ]
            rows.append([InlineKeyboardButton(text=common("cancel_button"), callback_data="debt:cancel")])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            await state.set_state(DebtState.select_acc)
            await _edit(
                message,
                state,
                fmsg(
                    "debts_recv_select_from",
                    counterparty=data.get("counterparty"),
                    amount=amount,
                    currency=currency,
                ),
                kb,
            )
            return

        # settle_recv: ask credit account
        if mode == "settle_recv":
            accs = (
                await session.execute(
                    select(Account)
                    .where(Account.user_id == user.id, Account.is_external_balance == False)
                    .order_by(Account.id.asc())
                )
            ).scalars().all()
            accs = [a for a in accs if a.currency == currency]
            if not accs:
                await state.clear()
                await message.answer(fmsg("debts_no_accounts_in"))
                return
            rows = [
                [InlineKeyboardButton(text=f"{a.name} ({a.currency})", callback_data=f"debt:to:{a.id}")]
                for a in accs
            ]
            rows.append([InlineKeyboardButton(text=common("cancel_button"), callback_data="debt:cancel")])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            await state.set_state(DebtState.select_acc)
            await _edit(
                message,
                state,
                fmsg(
                    "debts_settle_recv_select_to",
                    counterparty=data.get("counterparty"),
                    amount=amount,
                    currency=currency,
                ),
                kb,
            )
            return

        # payable modes: update debt balance only
        acc = await _upsert_debt_account(session, user.id, mode, data.get("counterparty"), currency)
        cur = Decimal(acc.external_balance or 0)
        if mode == "pay":
            acc.external_balance = cur + amount
            msg = fmsg(
                "debts_recorded_pay",
                counterparty=acc.name.split(":", 1)[1],
                amount=amount,
                currency=currency,
            )
        else:  # settle_pay
            acc.external_balance = max(Decimal("0"), cur - amount)
            msg = fmsg(
                "debts_settled_pay",
                counterparty=acc.name.split(":", 1)[1],
                amount=amount,
                currency=currency,
            )
        await session.commit()

    await state.clear()
    await message.answer(msg)


@router.callback_query(DebtState.select_acc, F.data.startswith("debt:to:"))
async def debt_settle_recv_select_account(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Credit account for debt repayment (settle_recv)."""
    try:
        acc_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer(fmsg("debts_account_error"), show_alert=True)
        return

    data = await state.get_data()
    amount = Decimal(str(data.get("amount")))
    currency = data.get("currency", "RUB")
    counterparty = data.get("counterparty") or dmsg("finance", "default_counterparty")

    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        account = (
            await session.execute(
                select(Account).where(Account.user_id == user.id, Account.id == acc_id, Account.is_external_balance == False)
            )
        ).scalar_one_or_none()
        if not account:
            await callback.answer(common("account_not_found"), show_alert=True)
            return
        if account.currency != currency:
            await callback.answer(
                common("account_currency_mismatch", account_currency=account.currency, currency=currency),
                show_alert=True,
            )
            return

        debt_acc = await _upsert_debt_account(session, user.id, "settle_recv", counterparty, currency)
        cur = Decimal(debt_acc.external_balance or 0)
        debt_acc.external_balance = max(Decimal("0"), cur - amount)

        occurred = _parse_occurred_at({})
        txn = Transaction(
            user_id=user.id,
            account_id=account.id,
            type="income",
            amount=amount,
            currency=account.currency,
            category=dmsg("finance", "debts_category"),
            description=dmsg("finance", "debt_return_description", counterparty=counterparty),
            occurred_at=occurred,
        )
        session.add(txn)
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        fmsg(
            "debts_settled_recv",
            counterparty=counterparty,
            amount=amount,
            currency=currency,
            account=account.name,
        ),
        reply_markup=_menu_kb(),
    )
    await callback.answer()


@router.callback_query(DebtState.select_acc, F.data.startswith("debt:from:"))
async def debt_select_account(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Debit account when recording a receivable (recv)."""
    try:
        acc_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer(fmsg("debts_account_error"), show_alert=True)
        return

    data = await state.get_data()
    amount = Decimal(str(data.get("amount")))
    currency = data.get("currency", "RUB")
    mode = data.get("mode")
    counterparty = data.get("counterparty") or dmsg("finance", "default_counterparty")

    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        account = (
            await session.execute(
                select(Account).where(Account.user_id == user.id, Account.id == acc_id, Account.is_external_balance == False)
            )
        ).scalar_one_or_none()
        if not account:
            await callback.answer(common("account_not_found"), show_alert=True)
            return

        if account.currency != currency:
            await callback.answer(
                common("account_currency_mismatch", account_currency=account.currency, currency=currency),
                show_alert=True,
            )
            return

        debt_acc = await _upsert_debt_account(session, user.id, mode, counterparty, currency)
        cur = Decimal(debt_acc.external_balance or 0)
        debt_acc.external_balance = cur + amount

        occurred = _parse_occurred_at({})
        txn = Transaction(
            user_id=user.id,
            account_id=account.id,
            type="expense",
            amount=amount,
            currency=account.currency,
            category=dmsg("finance", "debts_category"),
            description=dmsg("finance", "debt_issue_description", counterparty=counterparty),
            occurred_at=occurred,
        )
        session.add(txn)
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        fmsg(
            "debts_recorded_recv",
            counterparty=counterparty,
            amount=amount,
            currency=currency,
            account=account.name,
        ),
        reply_markup=_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "debt:cancel")
async def debt_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(common("cancelled"))
    await callback.answer()
