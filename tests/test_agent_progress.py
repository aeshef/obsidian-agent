"""Статус agent loop в Telegram — только имена tools, без PII."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.telegram.agent_progress import TelegramAgentProgress, format_progress_line


def test_format_progress_line_basic():
    assert format_progress_line(1, ["read_note", "search_index"]) == (
        "Шаг 1: read_note, search_index"
    )


def test_format_progress_line_truncates_many_tools():
    names = [f"tool_{i}" for i in range(10)]
    line = format_progress_line(2, names)
    assert line.startswith("Шаг 2: ")
    assert "(+4)" in line


def test_format_progress_line_empty_tools():
    assert format_progress_line(1, []) == "Шаг 1: …"


@pytest.mark.asyncio
async def test_answer_delta_concurrent_single_message():
    bot = MagicMock()
    sent = MagicMock(message_id=100)
    bot.send_message = AsyncMock(return_value=sent)
    bot.edit_message_text = AsyncMock()
    progress = TelegramAgentProgress(bot, chat_id=1)

    def _platform_int(section, key, default=0):
        if key == "answer_stream_min_chars":
            return 10
        if key == "answer_stream_edit_ms":
            return 0
        return default

    with patch("shared.telegram.agent_progress.answer_stream_enabled", return_value=True):
        with patch("shared.telegram.agent_progress.answer_draft_enabled", return_value=False):
            with patch("shared.telegram.agent_progress.platform_int", side_effect=_platform_int):
                await asyncio.gather(
                    progress.on_answer_delta("hello world one"),
                    progress.on_answer_delta("hello world one two"),
                    progress.on_answer_delta("hello world one two three"),
                )
    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count >= 1


@pytest.mark.asyncio
async def test_answer_delta_draft_then_finalize_send_message():
    bot = MagicMock()
    final_msg = MagicMock(message_id=200)
    bot.send_message = AsyncMock(return_value=final_msg)

    with patch("shared.telegram.agent_progress.answer_stream_enabled", return_value=True):
        with patch("shared.telegram.agent_progress.answer_draft_enabled", return_value=True):
            with patch(
                "shared.telegram.agent_progress.send_message_draft",
                new_callable=AsyncMock,
                return_value=True,
            ) as draft_mock:
                with patch(
                    "shared.telegram.agent_progress.platform_int",
                    side_effect=lambda _s, key, default=0: (
                        10 if key == "answer_stream_min_chars" else 0
                    ),
                ):
                    progress = TelegramAgentProgress(bot, chat_id=1)
                    await progress.on_answer_delta("draft stream text here")
                    assert progress._answer_stream_mode == "draft"
                    assert draft_mock.await_count >= 1
                    assert bot.send_message.await_count == 0

                    await progress.finalize_answer(
                        "draft stream text here final",
                        reply_markup=None,
                    )
    assert bot.send_message.await_count == 1
    assert progress.answer_delivered_in_chat()


@pytest.mark.asyncio
async def test_finalize_answer_edit_omits_reply_keyboard_markup():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    bot = MagicMock()
    sent = MagicMock(message_id=42)
    bot.send_message = AsyncMock(return_value=sent)
    bot.edit_message_text = AsyncMock()
    progress = TelegramAgentProgress(bot, chat_id=1)
    progress._answer_message_id = 42
    progress._last_pushed_answer_text = "old"
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠")]])
    await progress.finalize_answer("new final text", reply_markup=kb)
    bot.edit_message_text.assert_awaited_once()
    assert "reply_markup" not in (bot.edit_message_text.await_args.kwargs or {})
