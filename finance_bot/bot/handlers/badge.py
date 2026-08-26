"""Badge meal tracking: NLU flow, coaching, dashboard section."""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from functools import lru_cache

from bot.config_loader import get_badge_config, is_badge_enabled
from shared.domain_messages import dmsg
from bot.db import AsyncSessionLocal
from bot.models import Account, User
from bot.ui import fmsg
from bot.dashboard_templates import dtpl
from bot.services.badge_tracker import BadgeTracker
from bot.services.dashboard.charts import plot_stacked_bar_categories_png
from bot.services.dashboard.format import fmt_num

router = Router(name="finance_badge")

@lru_cache(maxsize=1)
def _badge_line_re() -> re.Pattern[str]:
    pat = dmsg("badge", "line_keyword_pattern", default="badge")
    return re.compile(pat, re.I)


def badge_category_name() -> str:
    cfg = get_badge_config()
    return str(cfg.get("category") or dmsg("badge", "default_category", default="")).strip()


def badge_write_context() -> dict[str, str]:
    cfg = get_badge_config()
    return {
        "account": str(cfg.get("account_name") or "Meal Badge"),
        "category": badge_category_name(),
    }


def is_badge_category_label(name: str) -> bool:
    return (name or "").strip() == badge_category_name()


def transaction_uses_badge(parsed: dict, *, badge_mode: bool = False) -> bool:
    if parsed.get("_force_non_badge"):
        return False
    if badge_mode:
        return True
    cat = (parsed.get("_found_category_name") or parsed.get("category") or "").strip()
    return is_badge_category_label(cat)


async def resolve_account_from_user_text(
    parsed: dict, telegram_id: int, source_text: str
) -> bool:
    """User text names a real non-badge account → use it (overrides badge menu / NLU badge default)."""
    from shared.finance.entity_names import find_matching_label, labels_equal, normalize_label

    tracker = BadgeTracker(get_badge_config())
    badge_name = tracker.account_name
    norm_text = normalize_label(source_text or "")

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not user:
            return False
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        names = [a.name for a in accounts if a.name]

        for name in sorted(names, key=lambda n: len(normalize_label(n)), reverse=True):
            if labels_equal(name, badge_name):
                continue
            nn = normalize_label(name)
            if len(nn) >= 4 and nn in norm_text:
                parsed["account"] = name
                parsed["_found_account_name"] = name
                parsed["_force_non_badge"] = True
                import logging

                logging.getLogger("finance.badge").info(
                    "account from user text: %r (matched %r)", name, source_text[:80]
                )
                return True

        acc_hint = (parsed.get("account") or "").strip()
        if acc_hint:
            found = find_matching_label(acc_hint, names)
            if found and not labels_equal(found, badge_name):
                parsed["account"] = found
                parsed["_found_account_name"] = found
                parsed["_force_non_badge"] = True
                return True
    return False


async def explicit_account_overrides_badge(parsed: dict, telegram_id: int) -> bool:
    """Compat wrapper — prefer resolve_account_from_user_text with source_text."""
    return await resolve_account_from_user_text(parsed, telegram_id, parsed.get("account") or "")


def infer_badge_spend_text(text: str) -> bool:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return False
    badge_lines = sum(1 for ln in lines if _badge_line_re().search(ln))
    return badge_lines > 0 and badge_lines >= max(1, len(lines) // 2)


def parsed_expenses_are_badge(parsed_list: list) -> bool:
    if not parsed_list:
        return False
    cat = badge_category_name()
    expenses = [p for p in parsed_list if p.get("type") == "expense"]
    if not expenses or len(expenses) != len(parsed_list):
        return False
    for p in expenses:
        name = (p.get("_found_category_name") or p.get("category") or "").strip()
        if name != cat:
            return False
    return True


async def ensure_badge_account(telegram_id: int) -> None:
    tracker = BadgeTracker(get_badge_config())
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if user is None:
            return
        await tracker.get_or_create_badge_account(session, user.id)
        await session.commit()


async def send_badge_coaching(
    bot: Any,
    chat_id: int,
    telegram_id: int,
    amount: float | int,
    comment: str | None,
) -> None:
    if not is_badge_enabled():
        return
    tracker = BadgeTracker(get_badge_config())
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if user is None:
            return
        acc = await tracker.get_or_create_badge_account(session, user.id)
        today = date.today()
        ds = await tracker.day_stats(session, user.id, today, acc.id)
        ms = await tracker.month_stats(session, user.id, today.year, today.month)
        tips = tracker.rule_coaching_after_spend(ds, ms, Decimal(str(amount)))
        llm_tip = await tracker.llm_coaching_after_spend(Decimal(str(amount)), comment, ds, ms)
        text = tracker.format_post_save_message(Decimal(str(amount)), comment, ds, ms, tips, llm_tip)
    await bot.send_message(chat_id=chat_id, text=text)


@router.callback_query(F.data == "action:badge")
async def badge_menu_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(badge_mode=True)
    ui = (get_badge_config().get("ui") or {})
    prompt = (ui.get("amount_prompt") or "").strip() or fmsg("badge_prompt").strip()
    await callback.message.answer(prompt)
    await callback.answer()


def build_badge_section(
    conn: sqlite3.Connection,
    user_id: int,
    charts_dir: Path,
    now: datetime,
    *,
    vault_root: Optional[Path] = None,
    chart_wikilink: Optional[Callable[[Path], str]] = None,
) -> list[str]:
    """Badge nutrition section for current month."""
    badge_png = charts_dir / dtpl("badge", "chart_file")
    if not is_badge_enabled():
        if badge_png.exists():
            badge_png.unlink()
        return []
    tracker = BadgeTracker(get_badge_config())
    cfg = get_badge_config()
    dash_cfg = cfg.get("dashboard") or {}
    title = dash_cfg.get("section_title") or dtpl("badge", "default_title", default="Badge")
    m = tracker.month_stats_sync(conn, user_id, now.year, now.month)
    if m is None:
        if badge_png.exists():
            badge_png.unlink()
        return [
            f"### {title}",
            "",
            dtpl("badge", "no_account"),
            "",
        ]
    lines = [
        f"### {title} ({now.strftime('%B %Y')})",
        "",
        dtpl("badge", "working_days", days=m.working_days),
        dtpl(
            "badge",
            "spent",
            spent=fmt_num(float(m.total_spent), decimals=0),
            entitlement=fmt_num(float(m.total_entitlement), decimals=0),
            pct=m.utilization_pct,
        ),
        dtpl("badge", "burned", amount=fmt_num(float(m.total_burned), decimals=0)),
    ]
    if dash_cfg.get("show_ndfl_estimate", False):
        lines.append(dtpl("badge", "ndfl", amount=fmt_num(float(m.total_ndfl), decimals=0)))
    lines.append(dtpl("badge", "zero_days", days=m.zero_spend_days))
    if float(m.total_over_limit) > 0:
        lines.append(dtpl("badge", "over_limit", amount=fmt_num(float(m.total_over_limit), decimals=0)))
    lines.append("")

    wdays = [d for d in m.days if d.is_working_day]
    if wdays:
        x_labels = [d.date.strftime("%d.%m") for d in wdays]
        spent_vals = [float(d.spent) for d in wdays]
        burned_vals = [float(d.burned) for d in wdays]
        ok = plot_stacked_bar_categories_png(
            x_labels,
            {dtpl("badge", "chart_spent"): spent_vals, dtpl("badge", "chart_burned"): burned_vals},
            title=dtpl("badge", "chart_title"),
            y_label="RUB",
            out_path=badge_png,
            show_total_labels=True,
            totals_for_labels=[float(d.limit) for d in wdays],
        )
        if ok:
            if chart_wikilink:
                lines.append(chart_wikilink(badge_png))
            elif vault_root is not None:
                rel = badge_png.resolve().relative_to(vault_root.resolve())
                lines.append(f"![[{rel.as_posix()}]]")
        elif badge_png.exists():
            badge_png.unlink()
        lines.append("")
    elif badge_png.exists():
        badge_png.unlink()

    return lines
