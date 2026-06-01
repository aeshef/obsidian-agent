"""Unified finance subsystem bootstrap (standalone bot and unified host)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.asyncio import AsyncEngine

from .db import Base, _engine
from .finance_db_paths import (
    bootstrap_canonical_from_replica_if_missing,
    detect_split_brain,
    log_finance_db_layout,
)
from .schema_migrate import run_schema_migrations

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger("finance.startup")


async def bootstrap_finance(
    engine: Optional[AsyncEngine] = None,
    *,
    bot: Optional["Bot"] = None,
    start_schedulers: bool = True,
) -> None:
    """
    Create tables, run migrations, enable WAL; log canonical/replica layout;
    optionally start APScheduler (broker sync, reminders).
    """
    from . import models  # noqa: F401 — register ORM models

    log_finance_db_layout()
    bootstrap_canonical_from_replica_if_missing()
    detect_split_brain()

    eng = engine or _engine
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_schema_migrations)

    if start_schedulers and bot is not None:
        from .scheduler import start_scheduler

        start_scheduler(bot)
        log.info("finance schedulers started")
