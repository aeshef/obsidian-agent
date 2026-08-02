"""Agent run jsonl traces."""
from __future__ import annotations

import json
from pathlib import Path

from shared.agent.trace import AgentRunTrace, start_run


def test_trace_writes_jsonl(tmp_path: Path, monkeypatch):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("AGENT_TRACE", "1")
    monkeypatch.setenv("AGENT_TRACE_PATH", str(path))
    tr = start_run(user_id=1, domain="finance", question="balance?")
    assert tr is not None
    tr.selected_tools = ["get_balance"]
    tr.add_llm(
        iteration=0,
        latency_ms=12.5,
        model="deepseek-chat",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        tool_calls=1,
    )
    tr.add_tools(iteration=1, names=["get_balance"])
    tr.finish(reason="answer", answer="ok")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["domain"] == "finance"
    assert row["total_tokens"] == 15
    assert row["end_reason"] == "answer"
