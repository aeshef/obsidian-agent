from __future__ import annotations
import json
import html
from typing import Optional
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.enums import ParseMode
from sqlalchemy import select, desc

from bot.ui import fmsg
from shared.ui import common

from ..db import AsyncSessionLocal
from ..models import User, Transaction, Account

router = Router()


async def _get_accounts_with_transactions(session, user_id: int) -> list[tuple[int, str]]:
    """Accounts that ever had transactions: (account_id, account_name)."""
    q = (
        await session.execute(
            select(Account.id, Account.name)
            .join(Transaction, Transaction.account_id == Account.id)
            .where(Transaction.user_id == user_id)
            .distinct()
            .order_by(Account.name)
        )
    )
    return [(row[0], (row[1] or fmsg("recent_default_account"))[:25]) for row in q.all()]


def _kb_last_menu(limit: int, accounts: list, filter_account_id: Optional[int] = None) -> InlineKeyboardMarkup:
    rows = []
    if filter_account_id is not None:
        rows.append([InlineKeyboardButton(text=fmsg("recent_all_accounts"), callback_data="last:all")])
    # One account per button row (2 per row)
    if accounts:
        for i in range(0, len(accounts), 2):
            pair = accounts[i : i + 2]
            row = [
                InlineKeyboardButton(text=f"💳 {name}", callback_data=f"last:acc:{aid}")
                for aid, name in pair
            ]
            rows.append(row)
    rows.append([InlineKeyboardButton(text=fmsg("recent_export_json"), callback_data="lastexport")])
    rows.append([InlineKeyboardButton(text=common("menu_home"), callback_data="action:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_last(tg_id: int, limit: int, account_id: Optional[int] = None) -> str:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            return common("need_start")
        q = (
            select(Transaction, Account)
            .join(Account, Account.id == Transaction.account_id)
            .where(Transaction.user_id == user.id)
        )
        if account_id is not None:
            q = q.where(Transaction.account_id == account_id)
        q = q.order_by(desc(Transaction.occurred_at), desc(Transaction.id)).limit(limit)
        result = await session.execute(q)
        rows = result.all()
        if not rows:
            return fmsg("recent_no_ops_account") if account_id else fmsg("recent_no_ops")
        lines = []
        for t, acc in rows:
            dt = t.occurred_at.strftime("%Y-%m-%d") if t.occurred_at else ""
            sign = "+" if t.type == "income" else "-"
            amt_str = f"{float(t.amount):.2f}"
            acc_name = (acc.name or "")[:18]
            cat = (t.category or "")[:18]
            descr = (t.description or "")[:24]
            line = f"{dt} {sign}{amt_str:>11} {t.currency:<4} {acc_name:<18} [{cat}] {descr}"
            lines.append(line.rstrip())
        content = "\n".join(lines)
        return f"<pre>{html.escape(content)}</pre>"


@router.callback_query(F.data == "action:last")
async def last_default(callback: types.CallbackQuery) -> None:
    tg_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            await callback.answer(common("need_start_short"))
            return
        accounts = await _get_accounts_with_transactions(session, user.id)
    text = await _render_last(tg_id, 20, account_id=None)
    kb = _kb_last_menu(20, accounts, filter_account_id=None)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        import logging
        log = logging.getLogger("finance.recent")
        log.warning("Failed to edit message in last_default: %s", e)
        await callback.message.answer(
            text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    await callback.answer()


@router.callback_query(F.data == "last:all")
async def last_show_all(callback: types.CallbackQuery) -> None:
    """Show recent operations across all accounts."""
    tg_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            await callback.answer(common("need_start_short"))
            return
        accounts = await _get_accounts_with_transactions(session, user.id)
    text = await _render_last(tg_id, 20, account_id=None)
    kb = _kb_last_menu(20, accounts, filter_account_id=None)
    await callback.message.edit_text(
        text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("last:acc:"))
async def last_filter_by_account(callback: types.CallbackQuery) -> None:
    """Show recent operations for selected account."""
    try:
        account_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer(common("error_generic"))
        return
    tg_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            await callback.answer(common("need_start_short"))
            return
        accounts = await _get_accounts_with_transactions(session, user.id)
    text = await _render_last(tg_id, 20, account_id=account_id)
    kb = _kb_last_menu(20, accounts, filter_account_id=account_id)
    await callback.message.edit_text(
        text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("last:") & ~F.data.startswith("last:acc:") & (F.data != "last:all"))
async def last_with_limit(callback: types.CallbackQuery) -> None:
    """Handle last:N limit callbacks (legacy buttons)."""
    try:
        limit = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    text = await _render_last(callback.from_user.id, limit)
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        accounts = await _get_accounts_with_transactions(session, user.id) if user else []
    await callback.message.edit_text(
        text,
        reply_markup=_kb_last_menu(limit, accounts),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await callback.answer()




@router.callback_query(F.data == "lastexport")
async def last_export(callback: types.CallbackQuery) -> None:
    tg_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            await callback.message.edit_text(common("need_start"), reply_markup=_kb_last_menu(20, []))
            await callback.answer()
            return
        q = (
            await session.execute(
                select(Transaction, Account)
                .join(Account, Account.id == Transaction.account_id)
                .where(Transaction.user_id == user.id)
                .order_by(desc(Transaction.occurred_at), desc(Transaction.id))
            )
        )
        rows = q.all()
        data = []
        for t, acc in rows:
            data.append({
                "id": t.id,
                "type": t.type,
                "amount": str(t.amount),
                "currency": t.currency,
                "category": t.category,
                "description": t.description,
                "occurred_at": t.occurred_at.isoformat() if t.occurred_at else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "account": {
                    "id": acc.id,
                    "name": acc.name,
                    "type": acc.type,
                    "currency": acc.currency,
                    "is_external_balance": acc.is_external_balance,
                }
            })
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    doc = BufferedInputFile(payload, filename="transactions.json")
    await callback.message.answer_document(doc, caption=fmsg("recent_export_caption", count=len(data)))
    await callback.answer()


