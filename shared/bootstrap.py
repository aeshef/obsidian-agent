"""Bootstrap single-bot host: dispatcher, middleware, polling."""
from __future__ import annotations

import logging
import os

from shared.telegram.bot_factory import create_bot
from aiogram import BaseMiddleware, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from shared.logging_setup import setup_logging
from shared.telegram.host.agent import build_host_agent_app
from shared.telegram.host.keyboards import configure_host_keyboards
from shared.telegram.host.router import router as host_router
from shared.telegram.host.wire import (
    include_finance_routers,
    include_host_voice,
    include_knowledge_ingest,
    include_planning_aux,
)
from shared.telegram.memory_handlers import memory_router

log = logging.getLogger("shared.telegram.host")


def resolve_host_token(
    *,
    primary_env: str = "TELEGRAM_UNIFIED_BOT_TOKEN",
    fallback_env: str = "TELEGRAM_BOT_TOKEN",
) -> str:
    return (os.environ.get(primary_env) or os.environ.get(fallback_env) or "").strip()


async def run_host_bot(
    *,
    token: str | None = None,
    token_env: str = "TELEGRAM_UNIFIED_BOT_TOKEN",
) -> None:
    setup_logging(level=logging.INFO)
    resolved = token or resolve_host_token(primary_env=token_env)
    if not resolved:
        raise RuntimeError(f"{token_env} or TELEGRAM_BOT_TOKEN required")

    os.environ.setdefault("DEPLOY_MODE", "single")
    configure_host_keyboards()

    from shared.capabilities.profile import (
        MODULE_FINANCE,
        MODULE_KNOWLEDGE,
        MODULE_PLANNING,
        CONNECTOR_KB_SERENDIPITY,
        get_capabilities,
    )

    prof = get_capabilities()
    log.info(
        "capabilities modules=%s sync_profile=%s",
        prof.enabled_modules(),
        prof.sync_profile,
    )

    planning_bot = None
    if prof.module(MODULE_PLANNING):
        try:
            from planning_bot.app.bot import PlanningBot

            planning_bot = PlanningBot()
        except Exception as e:
            log.warning("planning bot unavailable: %s", e)

    agent_app = build_host_agent_app(planning_bot)

    bot = create_bot(resolved, parse_mode=None)
    dp = Dispatcher(storage=MemoryStorage())

    class _Inject(BaseMiddleware):
        def __init__(self, app, planning):
            self._app = app
            self._planning = planning

        async def __call__(self, handler, event, data):
            data["agent_app"] = self._app
            data["planning"] = self._planning
            state = data.get("state")
            if state is not None and getattr(event, "from_user", None):
                try:
                    st_data = await state.get_data()
                    if st_data.get("bulk_ingest"):
                        from knowledge_bot.app.state import activate_bulk_ingest

                        activate_bulk_ingest(event.from_user.id)
                except Exception:
                    pass
            return await handler(event, data)

    dp.update.middleware(_Inject(agent_app, planning_bot))
    dp.include_router(memory_router)
    dp.include_router(host_router)
    include_host_voice(dp)
    if prof.module(MODULE_FINANCE):
        include_finance_routers(dp)
        try:
            from bot.startup import bootstrap_finance

            await bootstrap_finance(bot=bot, start_schedulers=True)
        except Exception as e:
            log.error("finance bootstrap failed: %s", e, exc_info=True)
            raise
    if planning_bot is not None and prof.module(MODULE_PLANNING):
        include_planning_aux(dp)
        from planning_bot.app.scheduling import run_startup_tasks, start_scheduler

        run_startup_tasks(planning_bot)
        start_scheduler(planning_bot, bot)
        log.info("planning schedulers started")

    if prof.module(MODULE_KNOWLEDGE) and prof.connector(CONNECTOR_KB_SERENDIPITY):
        try:
            from knowledge_bot.services.serendipity import start_serendipity_task

            start_serendipity_task(bot)
            log.info("knowledge serendipity loop started")
        except Exception as e:
            log.warning("knowledge serendipity unavailable: %s", e)

    if prof.module(MODULE_KNOWLEDGE):
        include_knowledge_ingest(dp)

    log.info("host bot started, domains=%s", agent_app.domains())
    await dp.start_polling(bot)
