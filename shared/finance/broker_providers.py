"""Broker portfolio sync providers (extend here for new APIs)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from finance_bot.bot.models import User  # type: ignore

SyncFn = Callable[["AsyncSession", "User"], Awaitable[str]]

_SUPPORTED = frozenset({"none", "tinkoff", "example"})


def supported_broker_providers() -> frozenset[str]:
    return _SUPPORTED


async def run_broker_sync(provider: str, session: "AsyncSession", user: "User") -> str:
    key = (provider or "none").strip().lower()
    if key == "none":
        raise ValueError("broker_sync provider is none")
    if key == "tinkoff":
        from finance_bot.bot.services.tinkoff_integration import sync_tinkoff_account

        return await sync_tinkoff_account(session, user)
    if key == "example":
        raise ValueError(
            "broker provider 'example' is a template stub — implement sync in "
            "shared/finance/broker_providers.py or set provider: tinkoff in broker_sync.yaml"
        )
    raise ValueError(
        f"unsupported broker_sync provider: {provider!r} "
        f"(supported: {', '.join(sorted(_SUPPORTED - {'none'}))})"
    )
