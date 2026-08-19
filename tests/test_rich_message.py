"""Rich Messages transport helpers."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from shared.telegram.messaging import send_long_message
from shared.telegram.rich_message import rich_max_chars, rich_messages_enabled


def test_rich_config_defaults(monkeypatch, tmp_path):
    from shared.agent import platform_config as pc

    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        "telegram:\n  rich_messages: 1\n  rich_max_chars: 12000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pc, "agent_config_dir", lambda: tmp_path)
    pc.load_platform_config.cache_clear()
    assert rich_messages_enabled() is True
    assert rich_max_chars() == 12000
    pc.load_platform_config.cache_clear()


def test_send_long_message_prefers_rich():
    bot = MagicMock()
    bot.send_message = AsyncMock()

    async def _run():
        with patch("shared.telegram.messaging.rich_messages_enabled", return_value=True):
            with patch(
                "shared.telegram.messaging.send_rich_message",
                new_callable=AsyncMock,
                return_value=MagicMock(message_id=1),
            ) as rich:
                await send_long_message(bot, 1, "# Hi\n\n**bold**")
                return rich

    rich = asyncio.run(_run())
    rich.assert_awaited_once()
    assert bot.send_message.await_count == 0


def test_send_long_message_plain_fallback():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=2))

    async def _run():
        with patch("shared.telegram.messaging.rich_messages_enabled", return_value=True):
            with patch(
                "shared.telegram.messaging.send_rich_message",
                new_callable=AsyncMock,
                return_value=None,
            ):
                await send_long_message(bot, 1, "**bold** answer")

    asyncio.run(_run())
    assert bot.send_message.await_count == 1
    sent = bot.send_message.await_args.args[1]
    assert "**" not in sent


def test_send_long_message_rich_false_skips_rich():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=3))

    async def _run():
        with patch("shared.telegram.messaging.rich_messages_enabled", return_value=True):
            with patch(
                "shared.telegram.messaging.send_rich_message",
                new_callable=AsyncMock,
            ) as rich:
                await send_long_message(
                    bot, 1, "Сводка:\n• Кандидаты: 2\n• #109: x", rich=False
                )
                return rich

    rich = asyncio.run(_run())
    rich.assert_not_awaited()
    assert bot.send_message.await_count == 1
    sent = bot.send_message.await_args.args[1]
    assert "#109" in sent
    assert "\n" in sent
