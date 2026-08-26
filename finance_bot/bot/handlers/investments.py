from typing import List, Tuple
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from finance_bot.bot.services.broker_portfolio_sync import sync_broker_portfolio_api
from ..db import AsyncSessionLocal
from sqlalchemy import select
from ..models import User, Account, Transaction
from bot.ui import fmsg
from shared.domain_messages import dmsg
from shared.ui import common

from ..config_loader import get_nlu_config
from decimal import Decimal

router = Router()


def _compact_inline_rows(rows: list[list[InlineKeyboardButton]]) -> list[list[InlineKeyboardButton]]:
    out: list[list[InlineKeyboardButton]] = []
    for row in rows:
        buttons = [btn for btn in row if (btn.text or "").strip()]
        if buttons:
            out.append(buttons)
    return out


def invest_menu_kb() -> InlineKeyboardMarkup:
    from shared.capabilities.finance_gates import broker_sync_enabled
    from shared.capabilities.finance_ui import invest_menu_visible
    from shared.capabilities.profile import CONNECTOR_MANUAL_BROKER, get_capabilities
    from shared.capabilities.ui_bindings import message_allowed

    rows: list[list[InlineKeyboardButton]] = []
    if not invest_menu_visible() or not message_allowed("finance", "menu", "invest"):
        rows.append([InlineKeyboardButton(text=common("menu_home"), callback_data="action:menu")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if broker_sync_enabled():
        sync_label = fmsg("inline_invest_sync")
        if sync_label:
            rows.append([InlineKeyboardButton(text=sync_label, callback_data="invest:sync")])
    if broker_sync_enabled() or get_capabilities().connector(CONNECTOR_MANUAL_BROKER):
        for key, cb in (
            ("inline_invest_topup", "invest:topup"),
            ("inline_invest_withdraw", "invest:withdraw"),
            ("inline_invest_details", "invest:details"),
        ):
            label = fmsg(key)
            if label:
                rows.append([InlineKeyboardButton(text=label, callback_data=cb)])
    rows.append([InlineKeyboardButton(text=common("menu_home"), callback_data="action:menu")])
    return InlineKeyboardMarkup(inline_keyboard=_compact_inline_rows(rows))


def _invest_back_row(*, details: bool = False) -> list[InlineKeyboardButton]:
    back_cb = "invest:details" if details else "action:invest"
    return [
        InlineKeyboardButton(text=common("back"), callback_data=back_cb),
        InlineKeyboardButton(text=common("menu_home"), callback_data="action:menu"),
    ]


@router.callback_query(F.data == "action:invest")
async def invest_menu(callback: types.CallbackQuery) -> None:
    try:
        await callback.message.edit_text(fmsg("invest_title"), reply_markup=invest_menu_kb())
    except Exception as e:
        import logging
        log = logging.getLogger("finance.investments")
        log.warning("Failed to edit invest_menu message: %s", e)
        await callback.message.answer(fmsg("invest_title"), reply_markup=invest_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "invest:sync")
async def invest_sync(callback: types.CallbackQuery) -> None:
    from shared.capabilities.finance_gates import broker_sync_enabled

    if not broker_sync_enabled():
        await callback.answer(fmsg("broker_connector_unavailable"), show_alert=True)
        return
    tg_id = callback.from_user.id
    try:
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
            if user is None:
                await callback.message.edit_text(common("need_start"), reply_markup=invest_menu_kb())
                await callback.answer()
                return
            text = await sync_broker_portfolio_api(session, user)
        await callback.message.edit_text(text, reply_markup=invest_menu_kb(), parse_mode="HTML")
    except Exception as e:
        import logging
        log = logging.getLogger("finance.investments")
        log.exception("invest_sync error")
        await callback.message.edit_text(
            fmsg("invest_sync_error", error=str(e)[:200]),
            reply_markup=invest_menu_kb(),
        )
    await callback.answer()


class TopUpState(StatesGroup):
    from_acc = State()
    amount = State()
    msg_id = State()


class WithdrawState(StatesGroup):
    to_acc = State()
    amount = State()
    fee = State()


def _kb_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_invest_back_row()])


@router.callback_query(F.data == "invest:topup")
async def topup_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        cards = (
            await session.execute(
                select(Account).where(
                    Account.user_id == user.id,
                    Account.is_external_balance == False,
                    Account.type.in_(["card", "wallet"]),
                )
            )
        ).scalars().all()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=a.name, callback_data=f"topup:from:{a.id}")] for a in cards]
        + [[InlineKeyboardButton(text=common("back"), callback_data="action:invest")]]
    )
    m = await message.edit_text(fmsg("invest_select_card"), reply_markup=kb)
    await state.update_data(msg_id=m.message_id)
    await state.set_state(TopUpState.from_acc)
    await callback.answer()


@router.callback_query(TopUpState.from_acc, F.data.startswith("topup:from:"))
async def topup_from(callback: types.CallbackQuery, state: FSMContext) -> None:
    from_id = int(callback.data.split(":")[-1])
    await state.update_data(from_id=from_id)
    await state.set_state(TopUpState.amount)
    await callback.message.edit_text(fmsg("invest_topup_amount"), reply_markup=_kb_cancel_menu())
    await callback.answer()


@router.message(TopUpState.amount)
async def topup_amount(message: types.Message, state: FSMContext) -> None:
    try:
        amt = Decimal(message.text.replace(",", "."))
        if amt <= 0:
            raise ValueError
    except Exception:
        await message.answer(fmsg("invest_invalid_amount"), reply_markup=_kb_cancel_menu())
        return
    data = await state.get_data()
    from_id = int(data.get("from_id"))
    # delete user amount message to keep chat clean
    try:
        await message.delete()
    except Exception as e:
        import logging
        log = logging.getLogger("finance.investments")
        log.debug("Failed to delete user message: %s", e)
    # expense on card only; portfolio sync is separate
    nlu_cfg = get_nlu_config()
    broker_cats = nlu_cfg.get("broker_categories", {})
    topup_category = broker_cats.get("topup") or dmsg("finance", "broker_topup")
    
    async with AsyncSessionLocal() as session:
        from_acc = (await session.execute(select(Account).where(Account.id == from_id))).scalar_one()
        session.add(Transaction(
            user_id=from_acc.user_id,
            account_id=from_acc.id,
            type="expense",
            amount=amt,
            currency=from_acc.currency,
            category=topup_category,
        ))
        await session.commit()
    await state.clear()
    await message.answer(fmsg("invest_topup_recorded", category=topup_category), reply_markup=invest_menu_kb())


@router.callback_query(F.data == "invest:withdraw")
async def withdraw_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        cards = (
            await session.execute(
                select(Account).where(
                    Account.user_id == user.id,
                    Account.is_external_balance == False,
                    Account.type.in_(["card", "wallet"]),
                )
            )
        ).scalars().all()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=a.name, callback_data=f"wd:to:{a.id}")] for a in cards]
        + [[InlineKeyboardButton(text=common("back"), callback_data="action:invest")]]
    )
    await message.edit_text(fmsg("invest_target_card"), reply_markup=kb)
    await state.set_state(WithdrawState.to_acc)
    await callback.answer()


@router.callback_query(WithdrawState.to_acc, F.data.startswith("wd:to:"))
async def withdraw_to(callback: types.CallbackQuery, state: FSMContext) -> None:
    to_id = int(callback.data.split(":")[-1])
    await state.update_data(to_id=to_id)
    await callback.message.edit_text(fmsg("invest_amount_no_fee"), reply_markup=_kb_cancel_menu())
    await state.set_state(WithdrawState.amount)
    await callback.answer()


@router.message(WithdrawState.amount)
async def withdraw_amount(message: types.Message, state: FSMContext) -> None:
    try:
        amt = Decimal(message.text.replace(",", "."))
        if amt <= 0:
            raise ValueError
    except Exception:
        await message.answer(fmsg("invest_invalid_amount"), reply_markup=_kb_cancel_menu())
        return
    await state.update_data(wd_amount=str(amt))
    try:
        await message.delete()
    except Exception as e:
        import logging
        log = logging.getLogger("finance.investments")
        log.debug("Failed to delete user message: %s", e)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=fmsg("transfer_fee_zero"), callback_data="wdfee:0")],
            [InlineKeyboardButton(text=fmsg("transfer_fee_custom"), callback_data="wdfee:custom")],
            [InlineKeyboardButton(text=fmsg("sync_back_button"), callback_data="action:invest")],
        ]
    )
    await message.answer(fmsg("invest_broker_fee"), reply_markup=kb)


@router.callback_query(F.data == "wdfee:0")
async def wd_fee_zero(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.update_data(wd_fee="0")
    await _finalize_withdraw(callback, state)


@router.callback_query(F.data == "wdfee:custom")
async def wd_fee_custom(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(fmsg("invest_fee_amount"), reply_markup=_kb_cancel_menu())
    await state.set_state(WithdrawState.fee)
    await callback.answer()


@router.message(WithdrawState.fee)
async def wd_fee_value(message: types.Message, state: FSMContext) -> None:
    try:
        fee = Decimal(message.text.replace(",", "."))
        if fee < 0:
            raise ValueError
    except Exception:
        await message.answer(fmsg("invest_invalid_fee"), reply_markup=_kb_cancel_menu())
        return
    await state.update_data(wd_fee=str(fee))
    try:
        await message.delete()
    except Exception as e:
        import logging
        log = logging.getLogger("finance.investments")
        log.debug("Failed to delete user message: %s", e)
    await _finalize_withdraw(message, state)


async def _finalize_withdraw(evt, state: FSMContext) -> None:
    # evt may be callback.message or message
    is_callback = isinstance(evt, types.CallbackQuery)
    if is_callback:
        message = evt.message
        answer = evt.answer
    else:
        message = evt
        answer = (lambda *args, **kwargs: None)
    data = await state.get_data()
    to_id = int(data.get("to_id", 0))
    amt = Decimal(data.get("wd_amount", "0"))
    fee = Decimal(data.get("wd_fee", "0"))
    async with AsyncSessionLocal() as session:
        to_acc = (await session.execute(select(Account).where(Account.id == to_id))).scalar_one()
        nlu_cfg = get_nlu_config()
        broker_cats = nlu_cfg.get("broker_categories", {})
        withdraw_category = broker_cats.get("withdraw") or dmsg("finance", "broker_withdraw")
        fee_category = broker_cats.get("fee") or dmsg("finance", "broker_fee")

        # credit card
        session.add(Transaction(user_id=to_acc.user_id, account_id=to_acc.id, type="income", amount=amt, currency=to_acc.currency, category=withdraw_category))
        # fee as card expense when present
        if fee and fee > 0:
            session.add(Transaction(user_id=to_acc.user_id, account_id=to_acc.id, type="expense", amount=fee, currency=to_acc.currency, category=fee_category))
        await session.commit()
    await state.clear()
    text = fmsg("invest_withdraw_recorded", category=withdraw_category)
    kb = invest_menu_kb()
    if is_callback:
        try:
            await message.edit_text(text, reply_markup=kb)
        except Exception:
            await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)
    try:
        await answer()
    except Exception:
        pass

## Removed old broker_cash flow; now top-up only records expense from card


def _positions_menu_kb(accs: List[Tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"invest:acc:{acc_id}")] for name, acc_id in accs]
    rows.append(_invest_back_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "invest:details")
async def invest_details(callback: types.CallbackQuery) -> None:
    try:
        from tinkoff.invest import Client
    except ModuleNotFoundError:
        from ..services.tinkoff_integration import tinkoff_debug_text
        text = tinkoff_debug_text()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=fmsg("inline_invest_sync"), callback_data="invest:sync")],
                _invest_back_row(),
            ]
        )
        await callback.message.edit_text(fmsg("invest_details", text=text), reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return
    from ..config import get_settings
    token = get_settings().TINKOFF_API_TOKEN
    ignore_ids = set()
    if get_settings().TINKOFF_IGNORE_ACCOUNT_IDS:
        ignore_ids = set(x.strip() for x in get_settings().TINKOFF_IGNORE_ACCOUNT_IDS.split(",") if x.strip())
    accs_info: List[Tuple[str, str]] = []
    with Client(token) as client:
        accs = client.users.get_accounts().accounts
        from ..services.tinkoff_integration import _map_account_name  # reuse naming
        for a in accs:
            if getattr(a, "id", "") in ignore_ids:
                continue
            name = _map_account_name(a)
            accs_info.append((name, a.id))
    await callback.message.edit_text(fmsg("invest_select_account"), reply_markup=_positions_menu_kb(accs_info))
    await callback.answer()


@router.callback_query(F.data.startswith("invest:acc:"))
async def invest_show_positions(callback: types.CallbackQuery) -> None:
    try:
        from tinkoff.invest import Client
    except ModuleNotFoundError:
        await callback.message.edit_text(
            fmsg("invest_sdk_unavailable"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_invest_back_row(details=True)]),
        )
        await callback.answer()
        return
    acc_id = callback.data.split(":")[-1]
    from ..config import get_settings
    token = get_settings().TINKOFF_API_TOKEN
    lines = ["<pre>"]
    with Client(token) as client:
        p = client.operations.get_portfolio(account_id=acc_id)
        total = p.total_amount_portfolio
        tot_val = (total.units or 0) + (total.nano or 0)/1_000_000_000
        lines.append(dmsg("invest_report", "total_line", total=tot_val))
        for pos in p.positions:
            name = pos.instrument_type or "instrument"
            qty = (pos.quantity.units or 0) + (pos.quantity.nano or 0)/1_000_000_000
            valq = pos.current_price
            val = (valq.units or 0) + (valq.nano or 0)/1_000_000_000
            lines.append(f"{name:<16} {qty:>10.6f} @ {val:>10.2f}")
    text = "\n".join(lines + ["</pre>"])
    kb = InlineKeyboardMarkup(inline_keyboard=[_invest_back_row(details=True)])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()
