"""APScheduler setup and startup maintenance for planning_bot."""
from __future__ import annotations
from planning_bot.core.pdmsg import pdmsg
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
import pytz
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
TIMEZONE = os.environ.get('TIMEZONE') or os.environ.get('CALENDAR_TZ') or 'Europe/Moscow'
logger = logging.getLogger(__name__)
_scheduler: Optional[AsyncIOScheduler] = None

def start_scheduler(planning, bot: Bot) -> None:
    """Register daily jobs (mirrors former PTB job_queue schedule)."""
    from shared.capabilities.planning_gates import (
        planning_daily_checkin_enabled,
        planning_deadlines_alerts_enabled,
        planning_goals_alerts_enabled,
        planning_routines_enabled,
        planning_stuck_alerts_enabled,
        planning_task_id_maintenance_enabled,
        planning_weekly_review_enabled,
    )
    from planning_bot.services.daily_checkin_config import (
        checkin_schedule,
        replace_passive_evening_reminders,
    )
    from shared.telegram import push_policy as pp

    global _scheduler
    tz = pytz.timezone(TIMEZONE)
    _scheduler = AsyncIOScheduler(timezone=tz)
    if planning_weekly_review_enabled():
        _scheduler.add_job(
            planning.schedule_weekly_review,
            CronTrigger(day_of_week='sun', hour=6, minute=0, timezone=tz),
            args=[bot],
            id='weekly_review',
        )
    if planning_daily_checkin_enabled():
        hour, minute = checkin_schedule()
        _scheduler.add_job(
            planning.send_daily_checkin_prompt,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            args=[bot],
            id='daily_checkin_prompt',
        )
    brief_sources = (
        planning_routines_enabled()
        or planning_stuck_alerts_enabled()
        or planning_deadlines_alerts_enabled()
        or planning_goals_alerts_enabled()
    )
    if pp.morning_brief_enabled() and brief_sources:
        _scheduler.add_job(
            planning.send_morning_brief,
            CronTrigger(
                hour=pp.morning_brief_hour(),
                minute=pp.morning_brief_minute(),
                timezone=tz,
            ),
            args=[bot],
            id='morning_brief',
        )
        logger.info(
            "morning brief scheduled at %02d:%02d %s",
            pp.morning_brief_hour(),
            pp.morning_brief_minute(),
            TIMEZONE,
        )
    if planning_routines_enabled():
        for hour in pp.separate_morning_routine_hours():
            _scheduler.add_job(
                planning.send_morning_routine_reminder,
                CronTrigger(hour=hour, minute=0, timezone=tz),
                args=[bot],
                id=f'morning_routine_{hour}',
            )
        skip_evening_passive = (
            planning_daily_checkin_enabled() and replace_passive_evening_reminders()
        )
        if not skip_evening_passive:
            for hour in (21, 22, 23):
                _scheduler.add_job(
                    planning.send_evening_routine_reminder,
                    CronTrigger(hour=hour, minute=0, timezone=tz),
                    args=[bot],
                    id=f'evening_routine_{hour}',
                )

    async def daily_add_ids_to_tasks():
        try:
            logger.info(pdmsg("auto_5b5ba648c9"))  # log
            from planning_bot.tools.vault_maintenance import add_ids_to_tasks
            result = add_ids_to_tasks()
            if result:
                logger.info(pdmsg("auto_217da0a1be"))  # log
            else:
                logger.warning(pdmsg("auto_7bd2faab56"))  # log
        except Exception as e:
            logger.error(pdmsg("auto_5bae9513a0"), e, exc_info=True)  # log
    if planning_task_id_maintenance_enabled():
        _scheduler.add_job(
            daily_add_ids_to_tasks,
            CronTrigger(hour=0, minute=30, timezone=tz),
            id='daily_add_ids_to_tasks',
        )
    if planning_goals_alerts_enabled() and pp.separate_goals_alerts_enabled():
        _scheduler.add_job(
            planning.send_goals_alerts,
            CronTrigger(hour=7, minute=0, timezone=tz),
            args=[bot],
            id='daily_goals_alerts',
        )
    if planning_deadlines_alerts_enabled() and pp.separate_deadlines_alerts_enabled():
        _scheduler.add_job(
            planning.send_deadlines_alerts,
            CronTrigger(hour=6, minute=0, timezone=tz),
            args=[bot],
            id='daily_deadlines_alerts',
        )
    if planning_stuck_alerts_enabled() and pp.separate_stuck_alerts_enabled():
        _scheduler.add_job(
            planning.send_stuck_alerts,
            CronTrigger(hour=8, minute=0, timezone=tz),
            args=[bot],
            id='daily_stuck_alerts',
        )
    _scheduler.start()
    logger.info('APScheduler started (%s)', TIMEZONE)

def run_startup_tasks(planning) -> None:
    from shared.capabilities.planning_gates import (
        planning_daily_checkin_enabled,
        planning_routines_enabled,
    )

    if planning_daily_checkin_enabled():
        try:
            from planning_bot.services.signals_manager import ensure_signals_layout

            ensure_signals_layout()
        except Exception as e:
            logger.warning("signals layout ensure failed: %s", e)

    if planning_routines_enabled():
        try:
            from planning_bot.services.routines_layout import ensure_routines_layout

            actions = ensure_routines_layout()
            for line in actions:
                logger.info("routines layout: %s", line)
        except Exception as e:
            logger.warning("routines layout ensure failed: %s", e)

    if not planning_routines_enabled():
        logger.info("planning_routines feature off — skip routines_manager startup")
        return
    try:
        logger.info(pdmsg("auto_a60b6ad52e"))  # log
        routines_script = Path(__file__).resolve().parent.parent / 'services' / 'routines_manager.py'
        result = subprocess.run([sys.executable, str(routines_script)], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info(pdmsg("auto_55500c9703"))  # log
        else:
            logger.warning(pdmsg("auto_de473a4dde"), result.stderr)  # log
    except Exception as e:
        logger.warning(pdmsg("auto_a671ee6acb"), e)  # log
