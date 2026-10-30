"""Exercise authorization through the dispatcher, before domain handlers."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from shared.telegram.access import OwnerAccessMiddleware, configured_owner_id

OWNER = 123456
OTHER = 654321


@pytest.mark.parametrize('value', ['', ' ', 'username', '-1', '0', '1.0', '１２３'])
def test_invalid_owner_fails_closed(monkeypatch, value):
    monkeypatch.setenv('TELEGRAM_USER_ID', value)
    with pytest.raises(RuntimeError, match='TELEGRAM_USER_ID'):
        configured_owner_id()


def test_missing_owner_fails_closed(monkeypatch):
    monkeypatch.delenv('TELEGRAM_USER_ID', raising=False)
    with pytest.raises(RuntimeError):
        configured_owner_id()


def test_numeric_owner(monkeypatch):
    monkeypatch.setenv('TELEGRAM_USER_ID', f' {OWNER} ')
    assert configured_owner_id() == OWNER


def update(kind, user_id, chat_type='private', chat_id=None):
    user = {'id': user_id, 'is_bot': False, 'first_name': 'Test'}
    message = {'message_id': 1, 'date': 0, 'chat': {
        'id': user_id if chat_id is None else chat_id, 'type': chat_type,
    }, 'from': user, 'text': '/start'}
    payload = message if kind == 'message' else {
        'id': 'test', 'from': user, 'chat_instance': 'test',
        'message': message, 'data': 'menu:test',
    }
    return Update.model_validate({'update_id': 1, kind: payload})


@pytest.mark.parametrize('kind', ['message', 'callback_query'])
@pytest.mark.parametrize('user_id,chat_type,chat_id,allowed', [
    (OWNER, 'private', OWNER, True),
    (OTHER, 'private', OTHER, False),
    (OWNER, 'group', -123, False),
    (OTHER, 'group', -123, False),
    (OWNER, 'private', OTHER, False),
])
def test_dispatcher_gate(kind, user_id, chat_type, chat_id, allowed):
    async def run():
        dp = Dispatcher()
        gate = OwnerAccessMiddleware(OWNER)
        dp.update.outer_middleware(gate)
        handler = AsyncMock()
        async def receive(event):
            await handler(event)
        dp.message.register(receive)
        dp.callback_query.register(receive)
        bot = Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
        try:
            await dp.feed_update(bot, update(kind, user_id, chat_type, chat_id))
            assert handler.await_count == int(allowed)
        finally:
            await bot.session.close()
    asyncio.run(run())


@pytest.mark.parametrize('payload', [
    {'update_id': 1},
    {'update_id': 1, 'inline_query': {'id': 'test', 'from': {
        'id': OWNER, 'is_bot': False, 'first_name': 'Test',
    }, 'query': 'test', 'offset': ''}},
])
def test_unknown_and_chatless_updates_are_silent(payload):
    handler = AsyncMock()
    asyncio.run(OwnerAccessMiddleware(OWNER)(handler, Update.model_validate(payload), {}))
    handler.assert_not_awaited()
