"""One review screen for a multiline import; drafts never write financial rows."""
from __future__ import annotations
import asyncio
from collections import defaultdict
from html import escape
from uuid import uuid4
from aiogram import Router, F
from aiogram.types import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from sqlalchemy import select
from bot.db import AsyncSessionLocal
from bot.models import User
from bot.ui import fmsg
from bot.services.transactions import get_missing_fields
from bot.services.transaction_import import resolve_row, duplicate_ids, save_import, undo_import
from shared.agent.platform_config import platform_int

router = Router(name="finance_import_review")
_locks = defaultdict(asyncio.Lock)


def buttons(rows):
    return Markup(inline_keyboard=[[Button(text=label, callback_data=value) for label, value in row] for row in rows])


async def review(message, state, user_id):
    data = await state.get_data(); token = data["import_token"]; rows = data.get("transactions", [])
    ready, duplicates, missing = [], [], []
    seen = set()
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
        if not user: raise ValueError("unknown_user")
        for i, row in enumerate(rows):
            try:
                if await get_missing_fields(row, user_id, badge_mode=bool(data.get("badge_mode"))):
                    missing.append(i); continue
                values = await resolve_row(session, user.id, row)
            except (ValueError, TypeError): missing.append(i); continue
            key = (values["account_id"], values["type"], str(values["amount"]), values["currency"], str(values["occurred_at"].date()))
            if key in seen or await duplicate_ids(session, values): duplicates.append(i)
            seen.add(key); ready.append(i)
    allowed = ready if data.get("import_allow_duplicates") else [i for i in ready if i not in duplicates]
    await state.update_data(transactions=rows, import_ready=allowed)
    limit = platform_int("finance_import", "preview_rows", default=12)
    lines = [fmsg("import_summary", count=len(rows), ready=len(allowed), issues=len(data.get("import_issues", [])), duplicates=len(duplicates), missing=len(missing))]
    for i, row in enumerate(rows[:limit]):
        lines.append(fmsg("import_row", index=i+1, amount=escape(str(row.get("amount", "?"))), currency=escape(str(row.get("currency") or "")), account=escape(str(row.get("_found_account_name") or row.get("account") or "?")), date=escape(str(row.get("date") or row.get("occurred_at") or "?")), description=escape(str(row.get("description") or row.get("category") or "")[:80])))
    if duplicates: lines.append(fmsg("import_duplicate_rows", rows=", ".join(str(i+1) for i in duplicates)))
    if missing: lines.append(fmsg("import_missing_rows", rows=", ".join(str(i+1) for i in missing)))
    if len(rows)>limit: lines.append(fmsg("import_more", count=len(rows)-limit))
    for issue in data.get("import_issues", [])[:limit]:
        lines.append(fmsg("import_issue", line=issue["line"], text=escape(issue["text"][:100])))
    actions=[]
    if allowed: actions.append([(fmsg("import_save_ready"), f"imp:save:{token}")])
    actions.append([(fmsg("import_edit"), f"imp:edit:{token}"), (fmsg("import_details"), f"imp:details:{token}")])
    if duplicates: actions.append([(fmsg("import_toggle_duplicates"), f"imp:duplicates:{token}")])
    if data.get("import_issues"):
        actions.append([(fmsg("import_retry"),f"imp:retry:{token}"),(fmsg("import_repair"),f"imp:repair:{token}")])
    actions.append([(fmsg("confirm_cancelled_button"),f"imp:cancel:{token}")])
    text="\n".join(lines)
    if data.get("import_message_id"):
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=data["import_message_id"],text=text,reply_markup=buttons(actions),parse_mode="HTML")
            return
        except Exception: pass
    sent=await message.answer(text,reply_markup=buttons(actions),parse_mode="HTML")
    await state.update_data(import_message_id=sent.message_id)


@router.callback_query(F.data.startswith("imp:"))
async def action(callback, state):
    _, action, token = callback.data.split(":", 2)
    async with _locks[callback.from_user.id]:
        data=await state.get_data()
        if action=="undo":
            try:
                async with AsyncSessionLocal() as session, session.begin():
                    user=(await session.execute(select(User).where(User.telegram_id==callback.from_user.id))).scalar_one()
                    count=await undo_import(session,user.id,token)
                await callback.message.edit_text(fmsg("import_undone",count=count))
                await callback.answer()
                from bot.handlers.transactions_confirm import _mirror_db_replica_background
                await asyncio.to_thread(_mirror_db_replica_background)
            except ValueError: await callback.answer(fmsg("import_undo_changed"),show_alert=True)
            return
        if token!=data.get("import_token"):
            await callback.answer(fmsg("import_stale"),show_alert=True); return
        if action=="cancel":
            await state.clear();await callback.message.edit_text(fmsg("confirm_cancelled"));await callback.answer();return
        if action=="edit":
            await state.update_data(editing_field="import_patch")
            await callback.message.answer(fmsg("import_edit_prompt"));await callback.answer();return
        if action=="repair":
            await state.update_data(editing_field="import_repair")
            await callback.message.answer(fmsg("import_repair_prompt",count=len(data.get("import_issues",[]))))
            await callback.answer();return
        if action=="details":
            from bot.handlers.transactions.confirmation import show_transaction_confirmation
            if data.get("transactions"):
                await show_transaction_confirmation(data["transactions"][0],callback.message,state,0,len(data["transactions"]),tg_id=callback.from_user.id)
            await callback.answer();return
        if action=="duplicates": await state.update_data(import_allow_duplicates=not data.get("import_allow_duplicates"))
        if action=="retry":
            await callback.answer()
            from bot.services.nlu_parser import TransactionNLUParser
            issues=data.get("import_issues",[])
            report=await TransactionNLUParser().parse_report("\n".join(x["text"] for x in issues),telegram_id=callback.from_user.id)
            await state.update_data(transactions=data.get("transactions",[])+report.transactions,import_issues=report.issues)
        if action=="save":
            # Revalidate before commit; the database can have changed since preview.
            await review(callback.message,state,callback.from_user.id);data=await state.get_data()
            indices=data.get("import_ready",[])
            if not indices: await callback.answer(fmsg("import_nothing_ready"),show_alert=True);return
            try:
                async with AsyncSessionLocal() as session, session.begin():
                    user=(await session.execute(select(User).where(User.telegram_id==callback.from_user.id))).scalar_one()
                    saved=await save_import(session,user.id,token,[data["transactions"][i] for i in indices],allow_duplicates=bool(data.get("import_allow_duplicates")))
            except ValueError:
                await callback.answer(fmsg("import_recheck"),show_alert=True);return
            remaining=[row for i,row in enumerate(data["transactions"]) if i not in indices]
            await state.update_data(transactions=remaining,import_token=uuid4().hex,import_message_id=None,import_allow_duplicates=False)
            await callback.message.edit_text(fmsg("import_saved",count=len(saved)),reply_markup=buttons([[(fmsg("import_undo"),f"imp:undo:{token}")]]))
            from bot.handlers.transactions_confirm import _mirror_db_replica_background
            await asyncio.to_thread(_mirror_db_replica_background)
            if not remaining and not data.get("import_issues"):
                await state.clear();await callback.answer();return
        await review(callback.message,state,callback.from_user.id)
        await callback.answer()
