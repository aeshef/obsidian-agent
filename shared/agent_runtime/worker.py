"""Host-managed lifecycle; no independent scheduler or extra service."""

import asyncio
import logging

from .config import config, enabled
from .followups import tick

log = logging.getLogger(__name__)


async def run(app, bot):
    async def notify(job):
        from shared.i18n import msgf

        text = msgf(
            "agent",
            "followup_result",
            objective=job["objective"],
            status=job["status"],
            result=job["result"][: config()["notification_max_chars"]],
        )
        # Only jobs explicitly requested by their owner can reach this path.
        await bot.send_message(chat_id=job["user_id"], text=text, parse_mode=None)
        from shared.memory.session import append_turn

        append_turn(job["user_id"], "unified", "assistant", text)

    log.info("durable followup worker started; enabled=%s", enabled())
    while True:
        try:
            if enabled():
                await tick(app, notify)
        except Exception:
            log.exception("followup worker tick failed")
        await asyncio.sleep(config()["worker_interval_seconds"])
