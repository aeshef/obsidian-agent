"""Standalone knowledge bot: Telegram polling entrypoint."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Dispatcher, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from shared.logging_setup import add_rotating_file_handler, setup_logging
from shared.telegram.bot_factory import create_bot

from knowledge_bot.app.handlers.query import handle_message
from knowledge_bot.app.register_handlers import register_knowledge_callbacks
from knowledge_bot.core.config import load_config

logger = logging.getLogger("kb.main")


def configure_logging() -> None:
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(logging.INFO)
    add_rotating_file_handler(
        log_dir,
        filename="bot.log",
        max_bytes=10 * 1024 * 1024,
        backup_count=5,
    )
    for name in ("httpx", "httpcore", "aiogram"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def _run_polling() -> None:
    cfg = load_config()
    token = cfg.telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_KNOWLEDGE_BOT_TOKEN or TELEGRAM_BOT_TOKEN required")

    bot = create_bot(token, parse_mode=None)
    dp = Dispatcher(storage=MemoryStorage())
    register_knowledge_callbacks(dp)

    @dp.message(
        F.text
        | F.caption
        | F.photo
        | F.document
        | F.video
        | F.video_note
        | F.audio
        | F.voice,
    )
    async def _on_message(message: Message) -> None:
        await handle_message(message)

    try:
        from knowledge_bot.services.serendipity import start_serendipity_task

        start_serendipity_task(bot)
        logger.info("serendipity task started")
    except Exception as exc:
        logger.warning("serendipity unavailable: %s", exc)

    logger.info("knowledge_bot polling started")
    await dp.start_polling(bot)


def main() -> None:
    configure_logging()
    asyncio.run(_run_polling())


if __name__ == "__main__":
    main()
