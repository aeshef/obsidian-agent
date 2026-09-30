import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.methods import SendMessage, EditMessageText
from aiogram.types import MessageEntity
from shared.telegram.presentation import telegram_html, presentation_middleware


def test_safe_markup_and_literals():
    assert telegram_html('# Title\n\n**Result**\n- a < b & c') == '<b>Title</b>\n\n<b>Result</b>\n• a &lt; b &amp; c'
    assert telegram_html('`**literal**` #109 task_name') == '<code>**literal**</code> #109 task_name'
    assert telegram_html('```python\n<x> **raw**\n```') == '<pre>&lt;x&gt; **raw**\n</pre>'
    assert telegram_html('[a & b](https://example.org/?a=1&b=2)') == '<a href="https://example.org/?a=1&amp;b=2">a &amp; b</a>'
    assert telegram_html('<script>x</script>') == '&lt;script&gt;x&lt;/script&gt;'
    assert telegram_html('**unfinished') == '**unfinished'
    assert telegram_html('\x009999\x00') == '9999'


def test_send_edit_and_explicit_modes():
    async def run():
        bot = SimpleNamespace(default=SimpleNamespace(parse_mode=None))
        call = AsyncMock()
        for method in (SendMessage(chat_id=1,text='**Hi**'), EditMessageText(chat_id=1,message_id=2,text='**Hi**')):
            await presentation_middleware(call,bot,method)
            sent=call.call_args.args[1]
            assert sent.text == '<b>Hi</b>' and sent.parse_mode == 'HTML'
            assert method.text == '**Hi**'  # never mutate retries' input
        for method in (SendMessage(chat_id=1,text='<b>Hi</b>',parse_mode='HTML'),
                       SendMessage(chat_id=1,text='Hi',entities=[MessageEntity(type='bold',offset=0,length=2)])):
            await presentation_middleware(call,bot,method)
            assert call.call_args.args[1] is method
    asyncio.run(run())


def test_card_escapes_dynamic_values():
    from bot.handlers.transactions.confirmation import card
    assert '&lt;b&gt;' in card('confirm_preview_description',description='<b>unsafe</b>')
    rendered=card('confirm_preview_amount',amount=38557.25,currency='RUB')
    assert '38\u00a0557.25' in rendered


def test_bad_markup_falls_back_without_replaying_network_failures():
    from aiogram.exceptions import TelegramBadRequest
    async def run():
        method=SendMessage(chat_id=1,text='**_broken**_')
        bot=SimpleNamespace(default=SimpleNamespace(parse_mode=None))
        call=AsyncMock(side_effect=[TelegramBadRequest(method=method,message="can't parse entities"), 'ok'])
        assert await presentation_middleware(call,bot,method) == 'ok'
        assert call.call_args.args[1].parse_mode is None
        call=AsyncMock(side_effect=TimeoutError())
        try:
            await presentation_middleware(call,bot,method)
        except TimeoutError:
            pass
        else:
            assert False
        assert call.await_count == 1
    asyncio.run(run())
