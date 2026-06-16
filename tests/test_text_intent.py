"""text_intent classifier wiring (LLM mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from knowledge_bot.services.query.text_intent import classify_text_intent


@pytest.fixture
def agent_config(tmp_path: Path) -> Path:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "text_intent.txt").write_text("classifier prompt", encoding="utf-8")
    return tmp_path


def _llm_returning(intent: str) -> MagicMock:
    llm = MagicMock()
    resp = MagicMock()
    resp.content = {"intent": intent, "reason": "mock"}
    llm.chat_json.return_value = resp
    return llm


def test_classify_returns_chat_on_llm_failure(agent_config: Path) -> None:
    llm = MagicMock()
    llm.chat_json.side_effect = RuntimeError("timeout")
    assert classify_text_intent(agent_config, llm, "привет") == "chat"


def test_classify_brainstorm_example_as_chat(agent_config: Path) -> None:
    text = (
        "Я пытаюсь придумать вирусный проект на GitHub. "
        "Вот идеи: ## [[Пет-проекты]]\n- attention map\n"
        "но не могу выбрать простую проблему."
    )
    llm = _llm_returning("chat")
    assert classify_text_intent(agent_config, llm, text) == "chat"
    llm.chat_json.assert_called_once()


def test_classify_vault_search_as_query(agent_config: Path) -> None:
    llm = _llm_returning("query")
    assert (
        classify_text_intent(agent_config, llm, "есть ли у меня заметки про polymarket?")
        == "query"
    )
