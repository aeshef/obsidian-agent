"""Planned expense and forecast handlers."""

from datetime import datetime
from typing import Optional
from decimal import Decimal

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from ..db import AsyncSessionLocal
from ..models import User, PlannedExpense
from ..services.planning_forecast import generate_forecast, generate_month_plan_summary
from bot.ui import fmsg
from shared.ui import common

from ..config_loader import get_plan_parse_prompt
from ..llm import LLMClient
import logging

log = logging.getLogger("finance.planning")
router = Router()


class AddPlanState(StatesGroup):
    waiting_text = State()
    confirm = State()


async def _parse_plan_with_llm(text: str) -> Optional[dict]:
    """Parse free text into plan structure via LLM."""
    llm = LLMClient()
    try:
        resp = await llm.chat(
            messages=[
                {"role": "system", "content": get_plan_parse_prompt()},
                {"role": "user", "content": text},
            ]
        )
        if not resp:
            return None
        resp = resp.strip().replace("```json", "").replace("```", "").strip()
        import json
        d = json.loads(resp)
        return d
    except Exception as e:
        log.warning(f"LLM parse plan failed: {e}")
        return None


@router.callback_query(F.data == "action:forecast")
async def cmd_forecast(callback: types.CallbackQuery) -> None:
    """Forecast: how much to save."""
    await callback.answer()
    await callback.message.edit_text(fmsg("plan_progress"))
    try:
        text = await generate_forecast(callback.from_user.id)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=fmsg("plan_back"), callback_data="action:plan_list")],
        ])
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception as e:
        log.error(f"Forecast error: {e}", exc_info=True)
        await callback.message.edit_text(
            fmsg("plan_forecast_error", error=e),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=fmsg("plan_back"), callback_data="action:plan_list")],
            ]),
        )


@router.callback_query(F.data == "action:month_plan")
async def cmd_month_plan(callback: types.CallbackQuery) -> None:
    """Flexible spend for the current month."""
    await callback.answer()
    await callback.message.edit_text(fmsg("plan_progress"))
    try:
        text = await generate_month_plan_summary(callback.from_user.id)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=fmsg("plan_back"), callback_data="action:plan_list")],
        ])
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception as e:
        log.error(f"Month plan error: {e}", exc_info=True)
        await callback.message.edit_text(
            fmsg("plan_month_error", error=e),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=fmsg("plan_back"), callback_data="action:plan_list")],
            ]),
        )


@router.callback_query(F.data == "action:plan_list")
async def list_plans(callback: types.CallbackQuery) -> None:
    """List planned expenses."""
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        ).scalar_one_or_none()
        if not user:
            await callback.answer(common("error_generic"))
            return

        plans = (
            await session.execute(
                select(PlannedExpense)
                .where(PlannedExpense.user_id == user.id, PlannedExpense.status == "active")
                .order_by(PlannedExpense.due_date.asc().nullslast())
            )
        ).scalars().all()

    if not plans:
        text = fmsg("plan_list_empty")
    else:
        lines = [fmsg("plan_list_header")]
        for p in plans:
            due = p.due_date.strftime("%d.%m.%Y") if p.due_date else fmsg("plan_due_none")
            lines.append(
                fmsg(
                    "plan_list_line",
                    name=p.name,
                    amount=float(p.amount),
                    currency=p.currency,
                    due=due,
                )
            )
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fmsg("plan_add_btn"), callback_data="plan:add")],
        [InlineKeyboardButton(text=fmsg("plan_month_btn"), callback_data="action:month_plan")],
        [InlineKeyboardButton(text=fmsg("plan_forecast_btn"), callback_data="action:forecast")],
        [InlineKeyboardButton(text=fmsg("plan_back"), callback_data="action:menu")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "plan:add")
async def plan_add_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPlanState.waiting_text)
    await state.update_data(plan_msg_id=callback.message.message_id)
    await callback.message.edit_text(
        fmsg("plan_add_prompt"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=common("cancel_button"), callback_data="plan:cancel")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "plan:cancel")
async def plan_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await list_plans(callback)


@router.message(AddPlanState.waiting_text, F.text)
async def plan_add_text(message: types.Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text or len(text) < 5:
        await message.answer(fmsg("plan_parse_hint"))
        return

    parsed = await _parse_plan_with_llm(text)
    if not parsed:
        await message.answer(fmsg("plan_parse_fail"))
        return

    year = parsed.get("due_year") or datetime.now().year
    month = parsed.get("due_month")
    due_date = None
    if month:
        try:
            due_date = datetime(year, month, 1)
        except Exception:
            pass

    plan = {
        "name": parsed.get("name", fmsg("planning_default_name")),
        "amount": float(parsed.get("amount", 0)),
        "currency": parsed.get("currency", "RUB"),
        "due_date": due_date,
    }

    await state.update_data(plan=plan)
    await state.set_state(AddPlanState.confirm)

    due_str = due_date.strftime("%B %Y") if due_date else fmsg("plan_due_none")
    await message.answer(
        fmsg(
            "plan_confirm_create",
            name=plan["name"],
            amount=plan["amount"],
            currency=plan["currency"],
            due=due_str,
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=fmsg("plan_confirm_yes"), callback_data="plan:confirm_yes"),
                InlineKeyboardButton(text=fmsg("plan_confirm_no"), callback_data="plan:cancel"),
            ],
        ]),
    )


@router.callback_query(F.data == "plan:confirm_yes", AddPlanState.confirm)
async def plan_confirm_yes(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    plan = data.get("plan")
    if not plan:
        await state.clear()
        await callback.answer(common("error_generic"))
        return

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        ).scalar_one_or_none()
        if not user:
            await callback.answer(common("error_generic"))
            return

        pe = PlannedExpense(
            user_id=user.id,
            name=plan["name"],
            amount=Decimal(str(plan["amount"])),
            currency=plan["currency"],
            due_date=plan.get("due_date"),
            status="active",
        )
        session.add(pe)
        await session.commit()

    await state.clear()
    await callback.answer(fmsg("plan_added"))
    await callback.message.edit_text(
        fmsg("plan_added_detail", name=plan["name"], amount=plan["amount"], currency=plan["currency"]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=fmsg("plan_list_btn"), callback_data="action:plan_list")],
            [InlineKeyboardButton(text=fmsg("plan_menu_back"), callback_data="action:menu")],
        ]),
    )
