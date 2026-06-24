"""Background weekly synth + push candidates to Telegram."""
from __future__ import annotations

import logging
import os
from typing import Iterable

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from shared.i18n import msg, msgf
from shared.llm import LLMClient
from shared.memory.context_collectors import COLLECTORS
from shared.memory.insights import get_store
from shared.memory.synth import synthesize, synth_enabled
from shared.telegram.memory_ui import memory_open_callback
from shared.telegram_utils import split_message

log = logging.getLogger("shared.memory.synth_job")


def synth_domains() -> list[str]:
    raw = os.environ.get("SYNTH_DOMAINS", "finance,planning").strip()
    return [d.strip() for d in raw.split(",") if d.strip() in COLLECTORS]


def _notify_keyboard(pending_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=msg("synth", "remember_btn"),
                    callback_data=f"mem:ok:{pending_id}",
                ),
                InlineKeyboardButton(
                    text=msg("synth", "reject_btn"),
                    callback_data=f"mem:no:{pending_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=msg("synth", "open_memory_btn"),
                    callback_data=memory_open_callback(),
                ),
            ],
        ]
    )


async def notify_pushable(bot: Bot, chat_id: int, pushable: Iterable[tuple[int, str]], domain: str) -> None:
    for pid, pattern in pushable:
        header = msgf("synth", "pattern_ready", domain=domain, pattern=pattern)
        for chunk in split_message(header):
            await bot.send_message(chat_id, chunk, reply_markup=_notify_keyboard(pid))


async def run_weekly_synth_for_chat(
    bot: Bot,
    chat_id: int,
    llm: LLMClient | None = None,
    *,
    domains: list[str] | None = None,
) -> None:
    if not synth_enabled():
        log.debug("synth disabled (SYNTH_ENABLED)")
        return
    llm = llm or LLMClient()
    domains = domains or synth_domains()
    get_store().prune_expired()
    for domain in domains:
        collector = COLLECTORS.get(domain)
        if not collector:
            continue
        try:
            ctx_text = await collector(chat_id)
            if not ctx_text.strip():
                log.info("synth skip empty context domain=%s chat=%s", domain, chat_id)
                continue
            pushable = await synthesize(llm, domain, chat_id, ctx_text)
            if pushable:
                await notify_pushable(bot, chat_id, pushable, domain)
        except Exception as e:
            log.error("synth job domain=%s chat=%s: %s", domain, chat_id, e, exc_info=True)


async def run_weekly_synth_all_users(bot: Bot, llm: LLMClient | None = None) -> None:
    """Broadcast to chat_ids from env and/or finance DB."""
    if not synth_enabled():
        return
    chat_ids: set[int] = set()
    uid = os.environ.get("TELEGRAM_USER_ID", "").strip()
    if uid.isdigit():
        chat_ids.add(int(uid))
    try:
        from sqlalchemy import select

        from finance_bot.bot.db import AsyncSessionLocal
        from finance_bot.bot.models import User

        async with AsyncSessionLocal() as session:
            rows = await session.execute(select(User).where(User.chat_id.isnot(None)))
            for u in rows.scalars().unique().all():
                if u.chat_id:
                    chat_ids.add(int(u.chat_id))
    except Exception as e:
        log.debug("finance users for synth: %s", e)
    try:
        from planning_bot.core.config import CHAT_ID_FILE
        from planning_bot.app.chatid_store import load_chat_id

        cid = load_chat_id(CHAT_ID_FILE)
        if cid:
            chat_ids.add(cid)
    except Exception as e:
        log.debug("planning chat_id for synth: %s", e)

    for cid in chat_ids:
        await run_weekly_synth_for_chat(bot, cid, llm)
