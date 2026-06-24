"""Long agent answers must split for Telegram, not truncate."""
from __future__ import annotations


def test_split_message_produces_multiple_telegram_chunks():
    from shared.telegram.limits import max_message_chars
    from shared.telegram_utils import split_message

    limit = max_message_chars()
    text = ("абзац. " * 800).strip()
    chunks = split_message(text, max_len=limit)
    assert len(chunks) > 1
    assert all(len(c) <= limit for c in chunks)
    assert "абзац." in chunks[0]
    assert len("".join(chunks)) >= len(text) - 50
