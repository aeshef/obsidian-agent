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
        with patch("shared.telegram.agent_progress.platform_int", side_effect=_platform_int):
            await asyncio.gather(
                progress.on_answer_delta("hello world one"),
                progress.on_answer_delta("hello world one two"),
                progress.on_answer_delta("hello world one two three"),
            )
    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count >= 1
