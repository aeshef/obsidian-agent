"""Telegram: typing + short agent loop step status (no PII from tools)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Literal

from shared.agent.platform_config import platform_int
from shared.agent.progress import answer_draft_enabled, answer_stream_enabled
from shared.telegram.limits import max_message_chars, draft_max_chars
from shared.telegram.flood_guard import (
    edit_message_text_guarded,
    send_message_guarded,
)
from shared.telegram.message_draft import new_draft_id, send_message_draft
from shared.telegram_utils import split_message, strip_telegram_markdown

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger("shared.telegram.agent_progress")

StreamMode = Literal["draft", "edit"]


def _status_message_enabled() -> bool:
    return platform_int("agent_progress", "status_message", default=1) != 0


def _draft_stream_enabled() -> bool:
    return platform_int("agent_progress", "draft_stream", default=0) != 0


def format_progress_line(step: int, tool_names: list[str]) -> str:
    from shared.agent.platform_config import platform_int
    from shared.i18n import msg, msgf

    max_tools = platform_int("agent_progress", "max_tools_in_status", default=6)
    names = [n for n in tool_names if n][:max_tools]
    extra = len(tool_names) - len(names)
    tail = f" (+{extra})" if extra > 0 else ""
    joined = ", ".join(names) if names else msg("agent", "progress_empty_tools")
    return msgf("agent", "progress_line", step=step, tools=joined, tail=tail)


class TelegramAgentProgress:
    """Tool status: edit or draft. LLM answer: sendMessageDraft → final sendMessage."""

    def __init__(self, bot: "Bot", chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._status_message_id: int | None = None
        self._tool_draft_id = (chat_id % 2_000_000_000) or 1
        self._answer_draft_id: int | None = None
        self._answer_stream_mode: StreamMode | None = None
        self._answer_message_id: int | None = None
        self._answer_delivered = False
        self._last_answer_edit = 0.0
        self._pending_answer_text = ""
        self._last_pushed_answer_text = ""
        self._answer_lock = asyncio.Lock()

    async def on_tools_selected(self, tool_names: list[str]) -> None:
        try:
            await self._bot.send_chat_action(self._chat_id, "typing")
        except Exception as e:
            log.debug("chat_action typing: %s", e)

    async def on_tool_iteration(self, step: int, tool_names: list[str]) -> None:
        line = format_progress_line(step, tool_names)
        if _draft_stream_enabled():
            try:
                await send_message_draft(
                    self._bot,
                    chat_id=self._chat_id,
                    draft_id=self._tool_draft_id,
                    text=line[: draft_max_chars()],
                )
                return
            except Exception as e:
                log.debug("tool draft failed, fallback to status msg: %s", e)
        if not _status_message_enabled():
            return
        await self._update_status(line)

    async def on_answer_delta(self, text: str) -> None:
        if not answer_stream_enabled():
            return
        min_chars = platform_int("agent_progress", "answer_stream_min_chars", default=40)
        interval_ms = platform_int(
            "agent_progress",
            "answer_draft_interval_ms" if answer_draft_enabled() else "answer_stream_edit_ms",
            default=80 if answer_draft_enabled() else 900,
        )
        interval = interval_ms / 1000.0
        cap = max_message_chars()
        safe = strip_telegram_markdown(text or "")[:cap]
        self._pending_answer_text = safe
        if len(safe) < min_chars:
            return
        async with self._answer_lock:
            now = time.monotonic()
            if self._last_pushed_answer_text and (now - self._last_answer_edit) < interval:
                return
            self._last_answer_edit = now
            await self._push_answer_stream(safe)

    def answer_delivered_in_chat(self) -> bool:
        # With draft, final is not in history yet — finalize_answer required
        if self._answer_stream_mode == "draft":
            return self._answer_delivered
        return self._answer_delivered and self._answer_message_id is not None

    async def finalize_answer(self, text: str, *, reply_markup: Any = None) -> None:
        full = strip_telegram_markdown(text or "")
        if not full:
            return
        chunks = split_message(full, max_len=max_message_chars())
        async with self._answer_lock:
            if self._answer_stream_mode == "draft" or self._answer_message_id is None:
                await self._send_answer_chunks(chunks, reply_markup=reply_markup)
                self._answer_delivered = True
                self._last_pushed_answer_text = full
                self._pending_answer_text = full
                return
            if full == self._last_pushed_answer_text and len(chunks) <= 1:
                return
            try:
                await edit_message_text_guarded(
                    self._bot,
                    self._chat_id,
                    self._answer_message_id,
                    chunks[0],
                )
                if len(chunks) > 1:
                    await self._send_answer_chunks(
                        chunks[1:],
                        reply_markup=reply_markup,
                    )
                self._last_pushed_answer_text = full
                self._pending_answer_text = full
            except Exception as e:
                err = str(e).lower()
                if "message is not modified" in err and len(chunks) <= 1:
                    self._last_pushed_answer_text = full
                    self._pending_answer_text = full
                    return
                log.warning("finalize answer edit failed, sending chunks: %s", e)
                await self._send_answer_chunks(chunks, reply_markup=reply_markup)
                self._answer_delivered = True
                self._last_pushed_answer_text = full
                self._pending_answer_text = full

    async def _send_answer_chunks(
        self,
        chunks: list[str],
        *,
        reply_markup: Any = None,
    ) -> None:
        for i, chunk in enumerate(chunks):
            await send_message_guarded(
                self._bot,
                self._chat_id,
                chunk,
                reply_markup=reply_markup if i == len(chunks) - 1 else None,
            )

    async def on_complete(self) -> None:
        if self._status_message_id is not None:
            try:
                await self._bot.delete_message(self._chat_id, self._status_message_id)
            except Exception:
                pass
            self._status_message_id = None
        if (
            self._answer_stream_mode == "edit"
            and self._pending_answer_text
            and self._answer_message_id
        ):
            async with self._answer_lock:
                try:
                    await edit_message_text_guarded(
                        self._bot,
                        self._chat_id,
                        self._answer_message_id,
                        self._pending_answer_text,
                    )
                except Exception:
                    pass

    async def _push_answer_stream(self, safe: str) -> None:
        if answer_draft_enabled() and self._answer_stream_mode != "edit":
            if self._answer_draft_id is None:
                self._answer_draft_id = new_draft_id(self._chat_id)
            ok = await send_message_draft(
                self._bot,
                chat_id=self._chat_id,
                draft_id=self._answer_draft_id,
                text=safe,
            )
            if ok:
                self._answer_stream_mode = "draft"
                self._last_pushed_answer_text = safe
                return
            log.info("sendMessageDraft unavailable, fallback to edit_message for this answer")
            self._answer_stream_mode = "edit"
        await self._push_answer_edit(safe)

    async def _push_answer_edit(self, safe: str) -> None:
        if safe == self._last_pushed_answer_text:
            return
        self._answer_stream_mode = "edit"
        try:
            if self._answer_message_id is None:
                msg = await send_message_guarded(self._bot, self._chat_id, safe)
                self._answer_message_id = msg.message_id
                self._answer_delivered = True
            else:
                await edit_message_text_guarded(
                    self._bot,
                    self._chat_id,
                    self._answer_message_id,
                    safe,
                )
            self._last_pushed_answer_text = safe
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err:
                self._last_pushed_answer_text = safe
                return
            log.debug("answer stream edit failed: %s", e)

    async def _update_status(self, text: str) -> None:
        cap = platform_int("agent_progress", "status_max_chars", default=380)
        safe = (text or "")[: max(cap, 1)]
        try:
            if self._status_message_id is None:
                msg = await send_message_guarded(self._bot, self._chat_id, safe)
                self._status_message_id = msg.message_id
            else:
                await edit_message_text_guarded(
                    self._bot,
                    self._chat_id,
                    self._status_message_id,
                    safe,
                )
        except Exception as e:
            log.debug("status message update failed: %s", e)
