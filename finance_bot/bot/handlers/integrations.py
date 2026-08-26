from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from decimal import Decimal

from ..db import AsyncSessionLocal
from ..models import User, Account
from ..broker_portfolio import is_broker_portfolio_account
from ..services.tinkoff_integration import tinkoff_debug_text
from finance_bot.bot.services.broker_portfolio_sync import sync_broker_portfolio_api
from bot.ui import fmsg
from shared.i18n import msg
from shared.ui import common
from .start import main_menu_inline


router = Router()

_BROKER_SYNC_CMD = msg("finance", "exact_command_broker_sync")


class AddAccountState(StatesGroup):
    name = State()
    balance = State()
    currency = State()


def sync_menu_kb() -> InlineKeyboardMarkup:
    """Sync menu keyboard (labels from config/messages.ru.yaml)."""
    from shared.capabilities.finance_gates import broker_sync_enabled

    rows: list[list[InlineKeyboardButton]] = []
    if broker_sync_enabled():
        rows.append(
            [
                InlineKeyboardButton(
                    text=fmsg("sync_broker_button"),
                    callback_data="action:sync_broker",
                ),
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=fmsg("sync_add_account_button"),
                    callback_data="action:add_account",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=fmsg("sync_list_accounts_button"),
                    callback_data="action:list_accounts",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=fmsg("sync_back_button"),
                    callback_data="action:menu",
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "action:sync_menu")
async def sync_menu(callback: types.CallbackQuery) -> None:
    """Sync menu."""
    text = f"{fmsg('sync_menu_title')}\n\n{fmsg('sync_menu_choose')}"
    kb = sync_menu_kb()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        # Fallback to new message if edit fails
        import logging
        log = logging.getLogger("finance.integrations")
        log.warning("Failed to edit message in sync_menu: %s", e)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(F.text == _BROKER_SYNC_CMD)
async def sync_broker(message: types.Message) -> None:
    from shared.capabilities.finance_gates import broker_sync_enabled

    if not broker_sync_enabled():
        await message.answer(
            fmsg("connector_unavailable"),
            reply_markup=main_menu_inline(),
        )
        return
    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            await message.answer(common("need_start"))
            return
        text = await sync_broker_portfolio_api(session, user)
    await message.answer(text, reply_markup=sync_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "action:sync_broker")
async def sync_broker_cb(callback: types.CallbackQuery) -> None:
    from shared.capabilities.finance_gates import broker_sync_enabled

    if not broker_sync_enabled():
        await callback.answer(fmsg("broker_connector_unavailable"), show_alert=True)
        return
    await callback.message.edit_text(fmsg("sync_broker_progress"))
    message = callback.message
    tg_id = callback.from_user.id
    try:
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
            if user is None:
                await message.edit_text(common("need_start"), reply_markup=sync_menu_kb())
                return
            text = await sync_broker_portfolio_api(session, user)
        await callback.message.edit_text(text, reply_markup=sync_menu_kb(), parse_mode="HTML")
    except Exception as e:
        import logging
        log = logging.getLogger("finance.integrations")
        log.error("Broker sync error: %s", e, exc_info=True)
        await callback.message.edit_text(fmsg("sync_broker_error", error=e), reply_markup=sync_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "action:list_accounts")
async def list_accounts_cb(callback: types.CallbackQuery) -> None:
    """List all accounts."""
    tg_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            await callback.message.edit_text(common("need_start"), reply_markup=sync_menu_kb())
            await callback.answer()
            return
        
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id).order_by(Account.name))
        ).scalars().all()
        
        if not accounts:
            text = fmsg("accounts_empty")
        else:
            lines = [fmsg("accounts_header")]
            for acc in accounts:
                balance = ""
                if acc.is_external_balance and acc.external_balance is not None:
                    balance = fmsg(
                        "account_balance_suffix",
                        balance=acc.external_balance,
                        currency=acc.currency,
                    )
                elif is_broker_portfolio_account(acc.type, acc.is_external_balance):
                    balance = fmsg("account_portfolio_suffix")
                lines.append(f"• {acc.name} — {acc.type}{balance}")
            text = "\n".join(lines)
    
    await callback.message.edit_text(text, reply_markup=sync_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "action:add_account")
async def add_account_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start add-account wizard."""
    await callback.message.edit_text(
        f"{fmsg('add_account_title')}{fmsg('add_account_name_prompt')}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=common("cancel_button"), callback_data="action:sync_menu")]]
        ),
        parse_mode="HTML",
    )
    await state.set_state(AddAccountState.name)
    await callback.answer()


@router.callback_query(F.data == "action:sync_menu", AddAccountState.name)
@router.callback_query(F.data == "action:sync_menu", AddAccountState.balance)
@router.callback_query(F.data == "action:sync_menu", AddAccountState.currency)
async def cancel_add_account(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel add-account wizard."""
    await state.clear()
    await sync_menu(callback)


@router.message(AddAccountState.name)
async def add_account_name(message: types.Message, state: FSMContext) -> None:
    """Handle account name input."""
    name = message.text.strip()
    if not name or len(name) > 64:
        await message.answer(fmsg("add_account_name_invalid"))
        return
    
    await state.update_data(name=name)
    await message.answer(
        fmsg("add_account_balance_prompt"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=common("cancel_button"), callback_data="action:sync_menu")]]
        ),
    )
    await state.set_state(AddAccountState.balance)


@router.message(AddAccountState.balance)
async def add_account_balance(message: types.Message, state: FSMContext) -> None:
    """Handle balance input."""
    try:
        balance = Decimal(message.text.strip().replace(",", "."))
        if balance < 0:
            raise ValueError("Balance must be positive")
    except (ValueError, Exception):
        await message.answer(fmsg("add_account_balance_invalid"))
        return
    
    await state.update_data(balance=balance)
    await message.answer(
        fmsg("add_account_currency_prompt"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=common("cancel_button"), callback_data="action:sync_menu")]]
        ),
    )
    await state.set_state(AddAccountState.currency)


@router.message(AddAccountState.currency)
async def add_account_currency(message: types.Message, state: FSMContext) -> None:
    """Handle currency input and save account."""
    currency = message.text.strip().upper() if message.text.strip() != "/skip" else "RUB"
    if currency not in ["RUB", "USD", "EUR", "GBP", "CNY"]:
        await message.answer(fmsg("add_account_currency_invalid"))
        return
    
    data = await state.get_data()
    name = data.get("name")
    balance = data.get("balance", Decimal(0))
    
    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            await message.answer(common("need_start"))
            await state.clear()
            return
        
        # Skip if account already exists
        existing = (
            await session.execute(select(Account).where(Account.user_id == user.id, Account.name == name))
        ).scalar_one_or_none()
        
        if existing:
        # Update balance if account exists
            existing.external_balance = balance
            existing.currency = currency
            text = fmsg("account_updated", name=name, balance=balance, currency=currency)
        else:
            # Create new account
            from bot.services.transactions.core import infer_account_type

            acc_type = infer_account_type(name)
            account = Account(
                user_id=user.id,
                name=name,
                type=acc_type,
                currency=currency,
                is_external_balance=False,
                external_balance=balance,
            )
            session.add(account)
            text = fmsg("account_added", name=name, balance=balance, currency=currency)
        
        await session.commit()
    
    await state.clear()
    await message.answer(text, reply_markup=sync_menu_kb())


@router.callback_query(F.data == "action:tinkoff_debug")
async def tinkoff_debug_cb(callback: types.CallbackQuery) -> None:
    """Tinkoff debug info."""
    text = tinkoff_debug_text()
    await callback.message.edit_text(text, reply_markup=sync_menu_kb())
    await callback.answer()

