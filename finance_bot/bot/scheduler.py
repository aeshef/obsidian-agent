from __future__ import annotations
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz
from sqlalchemy import select

from .services.subscriptions import load_subscriptions, format_subscription_line, is_due_within
from shared.finance.broker_portfolio_sync import sync_broker_portfolio_api
from .services.financial_analyst import FinancialAnalyst
from .services.badge_tracker import BadgeTracker
from .config_loader import get_badge_config, is_badge_enabled
from .config_loader import load_text_config
from .db import AsyncSessionLocal
from .models import User
from .config import get_settings
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.menu_labels import fin_menu
from bot.ui import fmsg

log = logging.getLogger("finance.scheduler")
scheduler: Optional[AsyncIOScheduler] = None


async def _get_users_with_chat_id(session) -> list:
    """Users with chat_id set."""
    result = await session.execute(select(User).where(User.chat_id.isnot(None)))
    return list(result.scalars().unique().all())


async def send_subscriptions_digest(bot) -> None:
    from shared.i18n import msg
    from shared.telegram.push_format import format_push

    try:
        subs = load_subscriptions()
        due = [s for s in subs if is_due_within(s, 3)]
        if not due:
            return
        body = "\n".join(f"• {format_subscription_line(s)}" for s in due)
        text = format_push(msg("push", "finance_subs_title") or fmsg("scheduler_subscriptions_header"), body)

        async with AsyncSessionLocal() as session:
            users = await _get_users_with_chat_id(session)
            for u in users:
                try:
                    await bot.send_message(chat_id=u.chat_id, text=text)
                except Exception as e:
                    log.warning("send_subscriptions_digest: failed user_id=%s: %s", u.id, e)
    except Exception as e:
        log.error(f"send_subscriptions_digest: {e}", exc_info=True)


async def run_daily_broker_sync() -> None:
    """Daily quiet broker sync; writes today's balance snapshot."""
    if not get_settings().TINKOFF_API_TOKEN:
        log.warning("run_daily_broker_sync: skip — TINKOFF_API_TOKEN not set")
        return
    failures = 0
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User))
            users = list(result.scalars().unique().all())
            for user in users:
                try:
                    await sync_broker_portfolio_api(session, user)
                    log.info("run_daily_broker_sync: portfolio sync ok user_id=%s", user.id)
                except ValueError as e:
                    log.debug("run_daily_broker_sync: skip user_id=%s (%s)", user.id, e)
                except Exception as e:
                    log.warning("run_daily_broker_sync: user_id=%s error: %s", user.id, e)
                    failures += 1
        if failures:
            raise RuntimeError(f"broker sync failed for {failures} user(s)")
        from .finance_db_paths import mirror_canonical_to_vault_replica
        mirror_canonical_to_vault_replica()
    except Exception as e:
        log.error("run_daily_broker_sync: %s", e, exc_info=True)
        raise


async def _user_has_txn_today(session, user_id: int, tz_name: str) -> bool:
    from datetime import datetime, timedelta

    from sqlalchemy import func, select

    from .models import Transaction

    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Store occurred_at naive UTC-ish; compare local day window in UTC approx.
    start_utc = start.astimezone(pytz.UTC).replace(tzinfo=None)
    end_utc = (start + timedelta(days=1)).astimezone(pytz.UTC).replace(tzinfo=None)
    q = await session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.occurred_at >= start_utc,
            Transaction.occurred_at < end_utc,
        )
    )
    return int(q.scalar_one() or 0) > 0


async def send_daily_txn_reminder(bot) -> None:
    from shared.i18n import msg
    from shared.telegram.push_format import format_push
    from shared.telegram import push_policy as pp

    if not pp.finance_txn_reminder_enabled():
        return
    try:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=fin_menu("add_expense"), callback_data="action:add_expense"),
                    InlineKeyboardButton(text=fin_menu("add_income"), callback_data="action:add_income"),
                ],
                [InlineKeyboardButton(text=fin_menu("last_ops"), callback_data="action:last")],
            ]
        )
        tz_name = get_settings().TIMEZONE
        body = fmsg("scheduler_daily_reminder")
        text = format_push(msg("push", "finance_txn_title"), body)
        async with AsyncSessionLocal() as session:
            users = await _get_users_with_chat_id(session)
            for u in users:
                try:
                    if pp.finance_txn_reminder_only_if_no_txn():
                        if await _user_has_txn_today(session, u.id, tz_name):
                            continue
                    await bot.send_message(
                        chat_id=u.chat_id, text=text, reply_markup=kb
                    )
                except Exception as e:
                    log.warning("send_daily_txn_reminder: failed user_id=%s: %s", u.id, e)
    except Exception as e:
        log.error(f"send_daily_txn_reminder: {e}", exc_info=True)



async def send_daily_insight(bot) -> None:
    """Morning random-time finance insight (9:00–11:00)."""
    from shared.i18n import msg
    from shared.telegram.push_format import format_push

    try:
        analyst = FinancialAnalyst()
        async with AsyncSessionLocal() as session:
            users = await _get_users_with_chat_id(session)
            for u in users:
                try:
                    insight = await analyst.daily_insight(u.telegram_id)
                    if insight:
                        text = format_push(msg("push", "finance_insight_title"), insight)
                        await bot.send_message(chat_id=u.chat_id, text=text)
                except Exception as e:
                    log.warning("send_daily_insight: user_id=%s: %s", u.id, e)
    except Exception as e:
        log.error("send_daily_insight: %s", e, exc_info=True)


async def send_weekly_analysis(bot) -> None:
    """Sunday 19:00 weekly LLM analysis."""
    try:
        analyst = FinancialAnalyst()
        async with AsyncSessionLocal() as session:
            users = await _get_users_with_chat_id(session)
            for u in users:
                try:
                    text = await analyst.run_analysis(u.telegram_id, period="week")
                    if text:
                        await bot.send_message(
                            chat_id=u.chat_id, text=fmsg("scheduler_weekly_title", text=text)
                        )
                except Exception as e:
                    log.warning("send_weekly_analysis: user_id=%s: %s", u.id, e)
    except Exception as e:
        log.error("send_weekly_analysis: %s", e, exc_info=True)


async def send_badge_evening_alert(bot) -> None:
    """Evening alert when badge daily spend is low."""
    if not is_badge_enabled():
        return
    tracker = BadgeTracker(get_badge_config())
    try:
        async with AsyncSessionLocal() as session:
            users = await _get_users_with_chat_id(session)
            for u in users:
                try:
                    text = await tracker.today_alert_text(session, u.id)
                    if text:
                        await bot.send_message(chat_id=u.chat_id, text=text)
                except Exception as e:
                    log.warning("send_badge_evening_alert: user_id=%s: %s", u.id, e)
    except Exception as e:
        log.error("send_badge_evening_alert: %s", e, exc_info=True)


async def send_badge_monthly_digest(bot) -> None:
    """1st of month: previous month badge summary."""
    if not is_badge_enabled():
        return
    tracker = BadgeTracker(get_badge_config())
    cfg = get_badge_config()
    now = datetime.now(pytz.timezone(get_settings().TIMEZONE))
    if now.month == 1:
        y, m = now.year - 1, 12
    else:
        y, m = now.year, now.month - 1
    try:
        async with AsyncSessionLocal() as session:
            users = await _get_users_with_chat_id(session)
            for u in users:
                try:
                    stats = await tracker.month_stats(session, u.id, y, m)
                    text = tracker.format_month_summary(stats)
                    prompt_tpl = (cfg.get("llm") or {}).get("monthly_digest_prompt") or ""
                    if not prompt_tpl.strip():
                        prompt_tpl = load_text_config("badge_monthly_prompt.txt")
                    rules = (cfg.get("rules_context") or "").strip()
                    if prompt_tpl and (cfg.get("llm") or {}).get("monthly_digest_enabled", True):
                        analyst = FinancialAnalyst()
                        prompt = prompt_tpl.replace("{rules_context}", rules)
                        prompt = prompt.replace("{month_stats_json}", tracker.month_stats_json(stats))
                        prompt = prompt.replace("{daily_limit}", str(int(tracker.daily_limit)))
                        prompt = prompt.replace("{ndfl_pct}", str(int(float(tracker.ndfl_rate) * 100)))
                        llm_text = await analyst.llm.chat([
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": fmsg("scheduler_badge_llm_prompt")},
                        ])
                        if llm_text and llm_text.strip():
                            text = text + "\n\n" + llm_text.strip()
                    await bot.send_message(chat_id=u.chat_id, text=text)
                except Exception as e:
                    log.warning("send_badge_monthly_digest: user_id=%s: %s", u.id, e)
    except Exception as e:
        log.error("send_badge_monthly_digest: %s", e, exc_info=True)


async def send_monthly_analysis(bot) -> None:
    """1st of month 09:00 — LLM analysis of previous month."""
    try:
        analyst = FinancialAnalyst()
        async with AsyncSessionLocal() as session:
            users = await _get_users_with_chat_id(session)
            for u in users:
                try:
                    text = await analyst.run_calendar_month_analysis(u.telegram_id)
                    if text:
                        await bot.send_message(
                            chat_id=u.chat_id, text=fmsg("scheduler_monthly_title", text=text)
                        )
                except Exception as e:
                    log.warning("send_monthly_analysis: user_id=%s: %s", u.id, e)
    except Exception as e:
        log.error("send_monthly_analysis: %s", e, exc_info=True)


def start_scheduler(bot) -> None:
    global scheduler
    from shared.capabilities.finance_gates import broker_sync_enabled

    tz = pytz.timezone(get_settings().TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)
    if broker_sync_enabled():
        scheduler.add_job(run_daily_broker_sync, CronTrigger(hour=7, minute=0, timezone=tz))
    else:
        log.info("broker_sync connector off — skip daily broker sync job")
    from shared.telegram import push_policy as pp

    scheduler.add_job(send_subscriptions_digest, CronTrigger(hour=10, minute=0, timezone=tz), args=[bot])
    if pp.finance_txn_reminder_enabled():
        scheduler.add_job(
            send_daily_txn_reminder,
            CronTrigger(
                hour=pp.finance_txn_reminder_hour(),
                minute=pp.finance_txn_reminder_minute(),
                timezone=tz,
            ),
            args=[bot],
        )
    scheduler.add_job(send_weekly_analysis, CronTrigger(day_of_week="sun", hour=19, minute=0, timezone=tz), args=[bot])
    scheduler.add_job(send_monthly_analysis, CronTrigger(day=1, hour=9, minute=0, timezone=tz), args=[bot])
    if is_badge_enabled():
        alerts = get_badge_config().get("alerts") or {}
        eh = int(alerts.get("evening_hour", 19))
        em = int(alerts.get("evening_minute", 0))
        scheduler.add_job(send_badge_evening_alert, CronTrigger(hour=eh, minute=em, timezone=tz), args=[bot])
        scheduler.add_job(
            send_badge_monthly_digest,
            CronTrigger(day=1, hour=9, minute=30, timezone=tz),
            args=[bot],
        )
    scheduler.add_job(
        send_daily_insight,
        CronTrigger(day_of_week="mon,wed,fri", hour=9, minute=0, timezone=tz),
        args=[bot],
        jitter=7200,
    )

    async def weekly_memory_synth():
        from shared.memory.synth_job import run_weekly_synth_all_users

        await run_weekly_synth_all_users(bot)

    scheduler.add_job(
        weekly_memory_synth,
        CronTrigger(day_of_week="sun", hour=4, minute=30, timezone=tz),
    )
    scheduler.start()
