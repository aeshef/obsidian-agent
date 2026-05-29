"""shared.llm JSON-mode prompt guard (DeepSeek requirement)."""
from shared.llm import _ensure_json_in_prompt


def test_ensure_json_in_prompt_adds_hint_when_missing():
    out = _ensure_json_in_prompt("Tag these notes.")
    assert "json" in out.lower()
    assert "Tag these notes." in out


def test_ensure_json_in_prompt_unchanged_when_present():
    prompt = "Return a JSON array of tags."
    assert _ensure_json_in_prompt(prompt) == prompt
