"""Message proxy with ASR/overridden text (voice/audio hidden — no duplicate ASR)."""
from __future__ import annotations

from aiogram.types import Message


class MessageWithText:
    """Message proxy with ASR text; voice/audio hidden — no duplicate ASR."""

    __slots__ = ("_message", "text")

    def __init__(self, message: Message, text: str) -> None:
        self._message = message
        self.text = text

    def __getattr__(self, name: str):
        return getattr(self._message, name)

    @property
    def voice(self):
        return None

    @property
    def audio(self):
        return None
