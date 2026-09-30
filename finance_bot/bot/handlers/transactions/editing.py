"""Transaction confirmation handlers."""
import logging

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.ui import fmsg
from shared.ui import common

from bot.db import AsyncSessionLocal
from bot.models import User, Account
from bot.handlers.transactions import show_transaction_confirmation, ConfirmTransactionsState

log = logging.getLogger("finance.transactions.confirm")

router = Router(name="transaction_editing")

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
            account = (await session.execute(select(Account).join(User).where(Account.id == account_id, User.telegram_id == callback.from_user.id))).scalar_one_or_none()
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
            account = (await session.execute(select(Account).join(User).where(Account.id == account_id, User.telegram_id == callback.from_user.id))).scalar_one_or_none()
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
            account = (await session.execute(select(Account).join(User).where(Account.id == account_id, User.telegram_id == callback.from_user.id))).scalar_one_or_none()
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

    if editing_field == "import_repair":
        from bot.services.nlu_parser import TransactionNLUParser
        from bot.handlers.transactions.import_review import review
        if len([x for x in text.splitlines() if x.strip()]) != len(data.get("import_issues", [])):
            await message.answer(fmsg("import_repair_prompt", count=len(data.get("import_issues", []))))
            return
        report = await TransactionNLUParser().parse_report(text, telegram_id=message.from_user.id)
        await state.update_data(transactions=transactions+report.transactions, import_issues=report.issues, editing_field=None)
        await review(message, state, message.from_user.id)
        return

    if editing_field == "import_patch":
        from bot.services.import_patch import apply_patch_text
        from bot.handlers.transactions.import_review import review
        try:
            updated = await apply_patch_text(transactions, text, message.from_user.id)
            await state.update_data(transactions=updated, editing_field=None, import_allow_duplicates=False)
            await review(message, state, message.from_user.id)
        except (ValueError, TypeError):
            await message.answer(fmsg("import_patch_invalid"))
        return

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
