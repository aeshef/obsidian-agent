"""Transaction confirmation handlers."""
from shared.finance.currency import base_currency
from decimal import Decimal
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.ui import fmsg
from shared.domain_messages import dmsg
from shared.ui import common

from ..db import AsyncSessionLocal
from ..models import User, Account, Transaction
from ..services.categories import load_categories
from ..services.financial_analyst import FinancialAnalyst
from .transactions import show_transaction_confirmation, ConfirmTransactionsState, _parse_occurred_at

log = logging.getLogger("finance.transactions.confirm")

router = Router()


def _mirror_db_replica_background() -> None:
    try:
        from ..finance_db_paths import mirror_canonical_to_vault_replica
        mirror_canonical_to_vault_replica()
    except Exception as e:
        log.warning("vault replica mirror after batch: %s", e)


async def _process_confirmed_transaction(
    session,
    user: User,
    parsed: dict,
    callback: types.CallbackQuery,
    *,
    badge_mode: bool = False,
) -> None:
    """Process confirmed transaction and persist to DB."""
    # account_balance
    if parsed.get("type") == "account_balance":
        account_name = parsed.get("account", fmsg("default_wallet_name"))
        balance = Decimal(str(parsed.get("balance", 0)))
        currency = parsed.get("currency") or base_currency()
        
        existing = (
            await session.execute(select(Account).where(Account.user_id == user.id, Account.name == account_name))
        ).scalar_one_or_none()
        
        if existing:
            existing.external_balance = balance
            existing.currency = currency
        else:
            from bot.services.transactions.core import infer_account_type

            acc_type = infer_account_type(account_name)
            account = Account(
                user_id=user.id,
                name=account_name,
                type=acc_type,
                currency=currency,
                is_external_balance=True,
                external_balance=balance,
            )
            session.add(account)
        
        await session.commit()
        await callback.answer(fmsg("confirm_account_updated_name", name=account_name))
        return
    
    # broker_withdraw
    if parsed.get("type") == "broker_withdraw":
        from .transactions import _handle_broker_withdraw
        await _handle_broker_withdraw(session, user, parsed, callback.message)
        await session.commit()
        await callback.answer(fmsg("confirm_broker_withdraw"))
        return
    
    # debt_settle_receivable
    if parsed.get("type") == "debt_settle_receivable":
        from .transactions import _get_or_create_account
        from .debts import _upsert_debt_account

        counterparty = parsed.get("counterparty") or dmsg("finance", "unknown_counterparty")
        amount = Decimal(str(parsed.get("amount", 0)))
        currency = parsed.get("currency") or base_currency()
        account_name = parsed.get("_found_account_name") or parsed.get("account")
        if not account_name:
            await callback.answer(fmsg("confirm_no_credit_account"), show_alert=True)
            return

        to_acc = await _get_or_create_account(session, user.id, account_name)
        if to_acc.currency != currency:
            await callback.answer(
                common("account_currency_mismatch", account_currency=to_acc.currency, currency=currency),
                show_alert=True,
            )
            return

        debt_acc = await _upsert_debt_account(session, user.id, "settle_recv", counterparty, currency)
        cur = Decimal(debt_acc.external_balance or 0)
        debt_acc.external_balance = max(Decimal("0"), cur - amount)

        occurred = _parse_occurred_at(parsed)
        session.add(Transaction(
            user_id=user.id,
            account_id=to_acc.id,
            type="income",
            amount=amount,
            currency=to_acc.currency,
            category=dmsg("finance", "debts_category"),
            description=dmsg("finance", "debt_return_description", counterparty=counterparty),
            occurred_at=occurred,
        ))
        await session.commit()
        await callback.answer(
            fmsg(
                "confirm_debt_recorded",
                counterparty=counterparty,
                amount=amount,
                currency=currency,
                to_account=to_acc.name,
            )
        )
        return

    # debt_receivable / debt_payable
    if parsed.get("type") in ["debt_receivable", "debt_payable"]:
        from .debts import _upsert_debt_account
        from .transactions import _get_or_create_account

        counterparty = parsed.get("counterparty") or dmsg("finance", "unknown_counterparty")
        amount = Decimal(str(parsed.get("amount", 0)))
        currency = parsed.get("currency") or base_currency()
        mode = "recv" if parsed.get("type") == "debt_receivable" else "pay"

        if mode == "recv":
            account_name = parsed.get("_found_account_name") or parsed.get("account")
            if not account_name:
                await callback.answer(fmsg("confirm_no_debit_account"), show_alert=True)
                return
            from_acc = await _get_or_create_account(session, user.id, account_name)
            if from_acc.currency != currency:
                await callback.answer(
                    common("account_currency_mismatch", account_currency=from_acc.currency, currency=currency),
                    show_alert=True,
                )
                return

            occurred = _parse_occurred_at(parsed)
            session.add(Transaction(
                user_id=user.id,
                account_id=from_acc.id,
                type="expense",
                amount=amount,
                currency=from_acc.currency,
                category=dmsg("finance", "debts_category"),
                description=dmsg("finance", "debt_issue_description", counterparty=counterparty),
                occurred_at=occurred,
            ))

        acc = await _upsert_debt_account(session, user.id, mode, counterparty, currency)
        cur = Decimal(acc.external_balance or 0)
        acc.external_balance = cur + amount

        await session.commit()
        if mode == "recv":
            msg = fmsg(
                "confirm_debt_recorded_recv",
                counterparty=counterparty,
                amount=amount,
                currency=currency,
                account=account_name,
            )
        else:
            msg = fmsg(
                "confirm_debt_recorded_simple",
                counterparty=counterparty,
                amount=amount,
                currency=currency,
            )
        await callback.answer(msg)
        return
    
    # expense / income / transfer
    if parsed.get("type") in ["expense", "income", "transfer"]:
        from .transactions import _get_or_create_account
        
        occurred = _parse_occurred_at(parsed)
        if parsed.get("type") == "transfer":
            from_acc = await _get_or_create_account(session, user.id, parsed.get("from_account"))
            to_acc = await _get_or_create_account(session, user.id, parsed.get("to_account"))
            amount = Decimal(str(parsed["amount"]))
            
            # debit from_account
            session.add(Transaction(
                user_id=user.id,
                account_id=from_acc.id,
                type="expense",
                amount=amount,
                currency=from_acc.currency,
                category=dmsg("finance", "transfer_category"),
                description=dmsg("finance", "transfer_to_description", account=to_acc.name),
                occurred_at=occurred,
            ))
            
            # credit to_account
            session.add(Transaction(
                user_id=user.id,
                account_id=to_acc.id,
                type="income",
                amount=amount,
                currency=to_acc.currency,
                category=dmsg("finance", "transfer_category"),
                description=dmsg("finance", "transfer_from_description", account=from_acc.name),
                occurred_at=occurred,
            ))
        else:
            from bot.services.transactions import resolve_expense_account

            account = await resolve_expense_account(
                session, user.id, parsed, badge_mode=badge_mode
            )
            
            txn = Transaction(
                user_id=user.id,
                account_id=account.id,
                type=parsed["type"],
                amount=Decimal(str(parsed["amount"])),
                currency=parsed.get("currency") or base_currency(),
                category=parsed.get("category"),
                description=parsed.get("description"),
                occurred_at=occurred,
            )
            session.add(txn)
        
        await session.commit()
        await callback.answer(fmsg("confirm_recorded"))


async def _run_quick_check(
    bot, telegram_id: int, chat_id: int, saved_transactions: List[Dict]
) -> None:
    """Runs a post-transaction smart check in the background; sends alert if warranted."""
    try:
        analyst = FinancialAnalyst()
        alert = await analyst.quick_check(telegram_id, saved_transactions)
        if alert:
            await bot.send_message(chat_id=chat_id, text=f"💡 {alert}")
    except Exception as e:
        log.debug("quick_check background task failed: %s", e)


@router.callback_query(F.data.startswith("txn:confirm:"))
async def confirm_transaction_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm transaction and save to DB."""
    try:
        index = int(callback.data.split(":")[-1])
        data = await state.get_data()
        transactions = data.get("transactions", [])
        
        log.info("Confirm transaction %s of %s user=%s", index, len(transactions), callback.from_user.id)
        
        if index >= len(transactions):
            log.error("Transaction %s not found (total %s)", index, len(transactions))
            await callback.answer(fmsg("confirm_tx_not_found"), show_alert=True)
            return
        
        parsed = transactions[index]
        log.info("Transaction %s: type=%s amount=%s", index, parsed.get("type"), parsed.get("amount"))
        
        async with AsyncSessionLocal() as session:
            tg_id = callback.from_user.id
            user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
            
            if not user:
                log.error("User %s not found on confirm", tg_id)
                await callback.answer(fmsg("confirm_user_not_found"), show_alert=True)
                return
            
            from .badge import transaction_uses_badge

            badge_save = transaction_uses_badge(
                parsed, badge_mode=bool(data.get("badge_mode"))
            )
            await _process_confirmed_transaction(
                session, user, parsed, callback, badge_mode=badge_save
            )
        
        # Remove confirmed txn from queue
        transactions.pop(index)
        
        log.info("Transactions remaining: %s", len(transactions))
        
        # Show next if any remain
        if transactions:
            # Index unchanged after pop
            next_index = index if index < len(transactions) else len(transactions) - 1
            await state.update_data(transactions=transactions, current_index=next_index)
            log.info("Next transaction %s (%s of %s)", next_index, next_index + 1, len(transactions))
            try:
                # Pass tg_id explicitly
                # Edit current callback message
                await show_transaction_confirmation(
                    transactions[next_index], 
                    callback.message, 
                    state, 
                    next_index, 
                    len(transactions),
                    tg_id=callback.from_user.id
                )
            except Exception as e:
                log.error("Failed to show next transaction: %s", e, exc_info=True)
                await callback.answer(fmsg("confirm_next_error"), show_alert=True)
        else:
            await state.clear()
            await callback.message.edit_text(fmsg("confirm_all_done"), reply_markup=None)
            asyncio.create_task(asyncio.to_thread(_mirror_db_replica_background))
            asyncio.create_task(
                _run_quick_check(callback.bot, callback.from_user.id, callback.message.chat.id, [parsed])
            )
            # Badge coaching after expense
            from .badge import send_badge_coaching, transaction_uses_badge

            if transaction_uses_badge(parsed, badge_mode=bool(data.get("badge_mode"))):
                asyncio.create_task(
                    send_badge_coaching(
                        callback.bot,
                        callback.message.chat.id,
                        callback.from_user.id,
                        parsed.get("amount", 0),
                        parsed.get("description"),
                    )
                )

        await callback.answer()
    except Exception as e:
        log.error("Transaction confirm failed: %s", e, exc_info=True)
        await callback.answer(common("error", error=e), show_alert=True)


@router.callback_query(F.data.startswith("txn:prev:"))
async def prev_transaction_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go to previous transaction."""
    index = int(callback.data.split(":")[-1])
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index > 0:
        prev_index = index - 1
        await state.update_data(current_index=prev_index)
        await show_transaction_confirmation(transactions[prev_index], callback.message, state, prev_index, len(transactions), tg_id=callback.from_user.id)
    
    await callback.answer()


@router.callback_query(F.data.startswith("txn:next:"))
async def next_transaction_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go to next transaction."""
    index = int(callback.data.split(":")[-1])
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index < len(transactions) - 1:
        next_index = index + 1
        await state.update_data(current_index=next_index)
        await show_transaction_confirmation(transactions[next_index], callback.message, state, next_index, len(transactions), tg_id=callback.from_user.id)
    
    await callback.answer()


@router.callback_query(F.data == "txn:cancel")
async def cancel_transactions_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel transaction confirmation flow."""
    await state.clear()
    await callback.message.edit_text(fmsg("confirm_cancelled"), reply_markup=None)
    await callback.answer()


@router.callback_query(F.data.startswith("txn:set_cat:"))
async def set_category_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Set category on pending transaction."""
    parts = callback.data.split(":")
    index = int(parts[2])
    category = ":".join(parts[3:])  # category may contain ":"
    
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index < len(transactions):
        transactions[index]["category"] = category
        await state.update_data(transactions=transactions)
        await show_transaction_confirmation(transactions[index], callback.message, state, index, len(transactions), tg_id=callback.from_user.id)
    
    await callback.answer()


@router.callback_query(F.data.startswith("txn:set_acc:"))
async def set_account_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Set account on pending transaction."""
    parts = callback.data.split(":")
    index = int(parts[2])
    account_id = int(parts[3])
    
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index < len(transactions):
        async with AsyncSessionLocal() as session:
            account = (await session.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
            if account:
                transactions[index]["account"] = account.name
                await state.update_data(transactions=transactions)
                await show_transaction_confirmation(transactions[index], callback.message, state, index, len(transactions), tg_id=callback.from_user.id)
    
    await callback.answer()


@router.callback_query(F.data.startswith("txn:set_from:"))
async def set_from_account_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Set transfer from_account."""
    parts = callback.data.split(":")
    index = int(parts[2])
    account_id = int(parts[3])
    
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index < len(transactions):
        async with AsyncSessionLocal() as session:
            account = (await session.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
            if account:
                transactions[index]["from_account"] = account.name
                await state.update_data(transactions=transactions)
                await show_transaction_confirmation(transactions[index], callback.message, state, index, len(transactions), tg_id=callback.from_user.id)
    
    await callback.answer()


@router.callback_query(F.data.startswith("txn:set_to:"))
async def set_to_account_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Set transfer/broker to_account."""
    parts = callback.data.split(":")
    index = int(parts[2])
    account_id = int(parts[3])
    
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index < len(transactions):
        async with AsyncSessionLocal() as session:
            account = (await session.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
            if account:
                transactions[index]["to_account"] = account.name
                await state.update_data(transactions=transactions)
                await show_transaction_confirmation(transactions[index], callback.message, state, index, len(transactions), tg_id=callback.from_user.id)
    
    await callback.answer()


@router.callback_query(F.data.startswith("txn:set_counterparty:"))
async def set_counterparty_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt counterparty for debt."""
    index = int(callback.data.split(":")[-1])
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index < len(transactions):
        await state.update_data(editing_field=f"counterparty:{index}")
        await callback.message.edit_text(
            fmsg("confirm_counterparty_prompt"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=common("cancel_button"), callback_data="txn:cancel")]]
            ),
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("txn:set_amount:"))
async def set_amount_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt amount."""
    index = int(callback.data.split(":")[-1])
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index < len(transactions):
        await state.update_data(editing_field=f"amount:{index}")
        await callback.message.edit_text(
            fmsg("confirm_amount_prompt"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=common("cancel_button"), callback_data="txn:cancel")]]
            ),
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("txn:set_cat_text:"))
async def set_category_text_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt category text."""
    index = int(callback.data.split(":")[-1])
    data = await state.get_data()
    transactions = data.get("transactions", [])
    
    if index < len(transactions):
        await state.update_data(editing_field=f"category:{index}")
        await callback.message.edit_text(
            fmsg("confirm_category_prompt"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=common("cancel_button"), callback_data="txn:cancel")]]
            ),
        )
    
    await callback.answer()


# Text input for missing fields
@router.message(ConfirmTransactionsState.transactions)
async def handle_transaction_field_input(message: types.Message, state: FSMContext) -> None:
    """Handle text input for missing transaction fields."""
    from unified_bot.host import labels as host_labels
    from unified_bot.host.keyboards import root_keyboard
    from unified_bot.host.menus import is_finance_menu, mode_from_button
    from shared.telegram.navigation import is_host_navigation
    from shared.i18n import msg

    text = (message.text or "").strip()
    if is_host_navigation(text) or text == host_labels.back_home():
        await state.clear()
        await message.answer(msg("host", "main_menu"), reply_markup=root_keyboard())
        return

    new_mode = mode_from_button(text)
    if new_mode:
        await state.clear()
        await state.update_data(ui_mode=new_mode, fixed_domain=new_mode)
        from unified_bot.host.dispatch import switch_mode

        await switch_mode(message, state, new_mode)
        return

    from bot.reply_menu import dispatch_reply_menu_button

    if is_finance_menu(text):
        await state.set_state(None)
        await state.update_data(editing_field=None, transactions=None, badge_mode=False)
        if await dispatch_reply_menu_button(message, state):
            return

    data = await state.get_data()
    editing_field = data.get("editing_field")
    transactions = data.get("transactions", [])

    if not editing_field or ":" not in editing_field:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        await message.answer(
            fmsg("nlu_pending_confirm"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=common("cancel_button"), callback_data="txn:cancel")]
                ]
            ),
        )
        return
    
    field_name, index_str = editing_field.split(":", 1)
    index = int(index_str)
    
    if index >= len(transactions):
        await message.answer(fmsg("confirm_tx_error"))
        await state.update_data(editing_field=None)
        return
    
    text = message.text.strip()
    
    # Delete user message
    try:
        await message.delete()
    except Exception as e:
        log.debug("Failed to delete user message: %s", e)
    
    # Update field
    if field_name == "counterparty":
        transactions[index]["counterparty"] = text
    elif field_name == "amount":
        try:
            transactions[index]["amount"] = float(text.replace(",", "."))
        except ValueError:
            await message.answer(fmsg("confirm_invalid_amount"))
            return
    elif field_name == "category":
        transactions[index]["category"] = text
    
    await state.update_data(transactions=transactions, editing_field=None)
    
    # Refresh confirmation UI
    await show_transaction_confirmation(
        transactions[index],
        message,
        state,
        index,
        len(transactions),
        tg_id=message.from_user.id
    )
