"""Bulk ingest: auto-save after pipeline (no per-note review)."""
from __future__ import annotations

import asyncio
import gc
import logging
from typing import Any

from aiogram.types import Message

from knowledge_bot.app import state as app_state
from knowledge_bot.app.save_note import commit_routed_note
from knowledge_bot.app.state import (
    bulk_record_failed,
    bulk_record_saved,
    bulk_session_stats,
    cleanup_media_group_after_delay,
)
from knowledge_bot.app.bulk_helpers import bulk_ack_every, bulk_should_skip_save
from knowledge_bot.app.ui import kmsg
from knowledge_bot.core.config import load_config

log = logging.getLogger("kb.bulk")


async def finish_bulk_ingest(
    main_message: Message,
    routed: dict[str, Any],
    summary_obj: dict[str, Any],
    rendered: str,
    *,
    uid: int,
    processing_msg: Message | None,
    media_group_id: int | None,
) -> None:
    """Persist note and send sparse progress acks (no preview keyboard)."""
    if processing_msg:
        try:
            await processing_msg.delete()
        except Exception:
            pass

    if media_group_id is not None and media_group_id in app_state._MEDIA_GROUPS:
        app_state._MEDIA_GROUPS[media_group_id]["processed"] = True
        app_state._MEDIA_GROUPS[media_group_id]["processing"] = False
        asyncio.create_task(cleanup_media_group_after_delay(media_group_id, delay=60))

    if bulk_should_skip_save(routed, summary_obj, rendered):
        bulk_record_failed(uid)
        failed = bulk_session_stats(uid)["failed"]
        try:
            await main_message.answer(kmsg("bulk_skip_empty", failed=failed))
        except Exception as send_err:
            log.warning("bulk skip notify failed: %s", send_err)
        gc.collect()
        return

    try:
        note_path = commit_routed_note(routed, summary_obj)
    except Exception as e:
        log.error("bulk save failed: %s", e, exc_info=True)
        bulk_record_failed(uid)
        failed = bulk_session_stats(uid)["failed"]
        try:
            await main_message.answer(
                kmsg("bulk_save_error", failed=failed, error=str(e)[:200])
            )
        except Exception as send_err:
            log.warning("bulk save error notify failed: %s", send_err)
        gc.collect()
        return

    bulk_record_saved(uid)
    stats = bulk_session_stats(uid)
    if stats["saved"] % bulk_ack_every() == 0:
        try:
            cfg = load_config()
            rel = note_path.relative_to(cfg.vault_path)
            await main_message.answer(
                kmsg(
                    "bulk_saved_ack",
                    saved=stats["saved"],
                    title=routed.get("title") or kmsg("untitled"),
                    path=rel,
                )
            )
        except Exception as send_err:
            log.warning("bulk saved ack failed: %s", send_err)

    gc.collect()
