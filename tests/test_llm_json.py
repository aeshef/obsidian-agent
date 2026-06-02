"""User-facing strings live in YAML configs."""
import json

import pytest

from shared.json_parse import LLMJsonParseError, parse_json_object, salvage_path_strings_from_text
from shared.llm import LLMClient, _ensure_json_in_prompt


def test_ensure_json_in_prompt_adds_hint_when_missing():
    out = _ensure_json_in_prompt("Tag these notes.")
    assert "json" in out.lower()
    assert "Tag these notes." in out


def test_ensure_json_in_prompt_unchanged_when_present():
    prompt = "Return a JSON array of tags."
    assert _ensure_json_in_prompt(prompt) == prompt


def test_parse_json_object_valid():
    obj = parse_json_object('{"paths": ["a/b.md"]}')
    assert obj["paths"] == ["a/b.md"]


def test_parse_json_object_salvage_truncated_paths(monkeypatch):
    monkeypatch.setenv("VAULT_REL_KNOWLEDGE", "Knowledge")
    from shared.agent.platform_config import load_platform_config

    load_platform_config.cache_clear()
    broken = '{"paths": ["Knowledge/AI/note.md", "Knowledge/foo'
    obj = parse_json_object(broken, finish_reason="length")
    assert "paths" in obj
    assert obj.get("_salvaged") is True
    assert any("AI" in p for p in obj["paths"])


def test_salvage_path_strings_from_text(monkeypatch):
    monkeypatch.setenv("VAULT_REL_KNOWLEDGE", "Knowledge")
    from shared.agent.platform_config import load_platform_config

    load_platform_config.cache_clear()
    text = '{"candidates": ["short/path.md", "Knowledge/x.md'
    got = salvage_path_strings_from_text(text)
    assert "short/path.md" in got
    assert "Knowledge/x.md" in got


def test_parse_json_object_empty_raises():
    with pytest.raises(LLMJsonParseError):
        parse_json_object("")


def test_chat_json_parse_failure_not_echo_prompt(monkeypatch):
    client = LLMClient(api_key="fake-key")

    def _fake_post(payload, timeout):
        return {
            "choices": [
                {
                    "message": {"content": '{"paths": ["broken'},
                    "finish_reason": "length",
                }
            ],
            "usage": {"completion_tokens": 900},
        }

    monkeypatch.setattr(client, "_post", _fake_post)
    result = client.chat_json("sys", "user", max_tokens=512)
    content = result.content
    assert content.get("_llm_error") != "llm_unavailable"
    assert "echo" not in content
    assert content.get("_salvaged") or content.get("_llm_error") == "json_parse" or "paths" in content


def test_chat_json_messages_raise_on_parse_error(monkeypatch):
    client = LLMClient(api_key="fake-key")

    def _fake_post(payload, timeout):
        return {
            "choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}],
        }

    monkeypatch.setattr(client, "_post", _fake_post)
    with pytest.raises(LLMJsonParseError):
        client.chat_json_messages(
            [{"role": "system", "content": "json out"}, {"role": "user", "content": "x"}],
            raise_on_error=True,
        )
