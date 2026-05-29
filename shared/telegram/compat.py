"""PTB-shaped adapters so planning_bot handlers work unchanged on aiogram."""
from __future__ import annotations

from aiogram.types import CallbackQuery, Message


class _VoiceProxy:
    def __init__(self, voice):
        self.file_id = voice.file_id


class MessageAdapter:
    """Wraps aiogram Message with reply_text / effective_chat like python-telegram-bot."""

    def __init__(self, message: Message):
        self._message = message
        self.text = message.text
        self.voice = _VoiceProxy(message.voice) if message.voice else None

    @property
    def effective_chat(self):
        return self._message.chat

    def get_bot(self):
        return self._message.bot

    async def reply_text(self, text, reply_markup=None, parse_mode=None):
        return await self._message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


class CallbackQueryAdapter:
    def __init__(self, callback: CallbackQuery):
        self._callback = callback
        self.data = callback.data
        self.from_user = callback.from_user

    async def answer(self):
        await self._callback.answer()

    async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
        await self._callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)


class UpdateAdapter:
    def __init__(self, event: Message | CallbackQuery):
        if isinstance(event, CallbackQuery):
            self.callback_query = CallbackQueryAdapter(event)
            self.message = None
            self._chat = event.message.chat if event.message else event.from_user
        else:
            self.message = MessageAdapter(event)
            self.callback_query = None
            self._chat = event.chat

    @property
    def effective_chat(self):
        return self._chat


class ContextAdapter:
    def __init__(self, bot, user_data: dict):
        self.bot = bot
        self.user_data = user_data


class ContextTypes:
    DEFAULT_TYPE = ContextAdapter
