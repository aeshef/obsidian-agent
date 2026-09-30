"""Transaction confirmation handlers."""
import asyncio
import logging
from typing import List, Dict

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from bot.ui import fmsg
from shared.ui import common

from ..db import AsyncSessionLocal
from ..models import User
from ..services.financial_analyst import FinancialAnalyst
from .transactions import show_transaction_confirmation

log = logging.getLogger("finance.transactions.confirm")

router = Router()
from bot.handlers.transactions.import_review import router as import_router
router.include_router(import_router)


def _mirror_db_replica_background() -> None:
    try:
        from ..finance_db_paths import mirror_canonical_to_vault_replica
        mirror_canonical_to_vault_replica()
    except Exception as e:
        log.warning("vault replica mirror after batch: %s", e)


from bot.handlers.transactions.persistence import _process_confirmed_transaction


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
    from bot.handlers.transactions.import_review import _locks
    async with _locks[callback.from_user.id]:
        await _confirm_transaction(callback, state)


async def _confirm_transaction(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm transaction and save to DB."""
    try:
        parts = callback.data.split(":")
        index = int(parts[2])
        data = await state.get_data()
        transactions = data.get("transactions", [])
        if len(parts) != 4 or parts[3] != data.get("confirm_revision"):
            await callback.answer(fmsg("import_stale"), show_alert=True)
            return
        await state.update_data(confirm_revision=None)

        log.info("Confirm transaction %s of %s user=%s", index, len(transactions), callback.from_user.id)

        if index < 0 or index >= len(transactions):
            log.error("Transaction %s not found (total %s)", index, len(transactions))
            await callback.answer(fmsg("confirm_tx_not_found"), show_alert=True)
            return

        parsed = transactions[index]
        from bot.services.transactions import get_missing_fields
        if await get_missing_fields(parsed, callback.from_user.id, badge_mode=bool(data.get("badge_mode"))):
            await show_transaction_confirmation(parsed, callback.message, state, index, len(transactions), tg_id=callback.from_user.id)
            await callback.answer(fmsg("import_nothing_ready"), show_alert=True)
            return
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
            saved = await _process_confirmed_transaction(
                session, user, parsed, callback, badge_mode=badge_save
            )

        if saved is False:
            await show_transaction_confirmation(parsed, callback.message, state, index, len(transactions), tg_id=callback.from_user.id)
            return

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
        elif data.get("import_issues"):
            from bot.handlers.transactions.import_review import review
            await state.update_data(transactions=[], wizard_message_id=None)
            await review(callback.message, state, callback.from_user.id)
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


from bot.handlers.transactions.editing import router as editing_router
router.include_router(editing_router)
