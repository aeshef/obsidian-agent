#!/usr/bin/env python3
"""
One-off Tinkoff broker sync (same as daily 7:00 job).
Run on server from finance_bot directory with .env loaded.

Used from sync_finance_db.sh before downloading finance.db to Mac
so the dashboard has up-to-date balances and today's snapshot.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


async def _main() -> None:
    from bot.db import _engine, Base
    from bot import models  # noqa: F401
    from bot.schema_migrate import run_schema_migrations
    from bot.scheduler import run_daily_broker_sync

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_schema_migrations)
    await run_daily_broker_sync()


if __name__ == "__main__":
    asyncio.run(_main())
