"""Broker portfolio API sync — provider selected in broker_sync.yaml."""
from __future__ import annotations

from typing import TYPE_CHECKING

from shared.finance.broker_providers import run_broker_sync
from shared.finance.broker_sync_config import broker_sync_provider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from finance_bot.bot.models import User  # type: ignore


async def sync_broker_portfolio_api(session: "AsyncSession", user: "User") -> str:
    """Run configured broker provider sync for one user."""
    return await run_broker_sync(broker_sync_provider(), session, user)
