"""Vault media album batching (no live Telegram)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.telegram.kb_media import send_vault_media_files


@pytest.mark.asyncio
async def test_photos_sent_as_album(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    # Force album on via platform defaults; monkeypatch helper.
    monkeypatch.setattr("shared.telegram.kb_media._album_enabled", lambda: True)
    monkeypatch.setattr("shared.telegram.kb_media._album_max", lambda: 10)

    vault = tmp_path / "vault"
    vault.mkdir()
    files = []
    for i in range(3):
        p = vault / f"c{i}.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n")
        files.append((p.name, f"cap{i}"))

    bot = MagicMock()
    bot.send_media_group = AsyncMock()
    bot.send_photo = AsyncMock()

    await send_vault_media_files(bot, chat_id=1, vault_path=vault, media_files=files)
    assert bot.send_media_group.await_count == 1
    media = bot.send_media_group.await_args.kwargs.get("media") or bot.send_media_group.await_args.args[1]
    assert len(media) == 3
    assert bot.send_photo.await_count == 0
