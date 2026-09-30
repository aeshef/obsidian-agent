import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import requests

from bot import llm as finance_llm
from bot.services.nlu_parser import TransactionNLUParser


def test_json_retries_connection_failure_and_preserves_errors(monkeypatch):
    monkeypatch.setattr(finance_llm, 'get_llm_config', lambda: {'retry': {'json_attempts': 2, 'backoff_seconds': 0}})
    client = finance_llm.LLMClient()
    calls = []
    def request(messages, **kwargs):
        calls.append(kwargs)
        assert kwargs['raise_on_error'] is True
        if len(calls) == 1:
            raise requests.ConnectTimeout('synthetic timeout')
        return {'transactions': [{'type': 'expense', 'amount': 12}]}
    monkeypatch.setattr(client, 'chat_json_messages', request)
    assert asyncio.run(client.chat_json([]))['transactions'][0]['amount'] == 12
    assert len(calls) == 2
    monkeypatch.setattr(client, 'chat_json_messages', lambda *a, **k: (_ for _ in ()).throw(requests.ConnectTimeout()))
    with pytest.raises(requests.ConnectTimeout):
        asyncio.run(client.chat_json([]))


def test_json_does_not_retry_auth_failure(monkeypatch):
    client = finance_llm.LLMClient()
    response = requests.Response(); response.status_code = 401
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(client, 'chat_json_messages', fail)
    with pytest.raises(requests.HTTPError):
        asyncio.run(client.chat_json([]))
    assert len(calls) == 1


def test_connect_timeout_separate_from_read(monkeypatch):
    client = finance_llm.LLMClient()
    monkeypatch.setattr(finance_llm, 'get_llm_config', lambda: {'timeout': {'connect': 7}})
    monkeypatch.setattr(finance_llm._SharedLLMClient, '_post', lambda self, payload, timeout: timeout)
    assert client._post({}, 120) == (7, 120)


def test_long_failed_input_gets_short_reply_without_confirmation(monkeypatch):
    from bot.handlers.transactions import nlu
    from bot.handlers import badge
    monkeypatch.setattr(badge, 'infer_badge_spend_text', lambda text: False)
    parser = SimpleNamespace(parse_report=AsyncMock(side_effect=requests.ConnectTimeout()))
    monkeypatch.setattr(nlu, 'TransactionNLUParser', lambda: parser)
    confirmation = AsyncMock()
    monkeypatch.setattr(nlu, 'show_transaction_confirmation', confirmation)
    progress = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    message = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock(return_value=progress))
    state = SimpleNamespace(get_data=AsyncMock(return_value={}), get_state=AsyncMock(return_value=None), update_data=AsyncMock(), set_state=AsyncMock())
    text = '28 August 100 lunch test account\n' * 120
    asyncio.run(nlu.process_transactions(text, message, state))
    assert message.answer.await_count == 2
    error = message.answer.call_args.args[0]
    assert error and len(error) < 1000 and text not in error
    confirmation.assert_not_awaited()
    state.set_state.assert_not_awaited()
    state.update_data.assert_not_awaited()
