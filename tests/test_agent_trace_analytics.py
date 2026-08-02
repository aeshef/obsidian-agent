"""Agent trace cost analytics + enriched jsonl fields."""
from __future__ import annotations

import json
from pathlib import Path

from shared.agent.trace import start_run
from shared.agent.trace_analytics import load_trace_rows, summarize_traces
from shared.agent.trace_cost import estimate_cost_usd


def test_estimate_cost_usd_scales():
    c = estimate_cost_usd(prompt_tokens=1_000_000, completion_tokens=0, model="")
    assert c > 0
    c2 = estimate_cost_usd(prompt_tokens=2_000_000, completion_tokens=0, model="")
    assert abs(c2 - 2 * c) < 1e-9


def test_trace_includes_cost_and_context(tmp_path: Path, monkeypatch):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("AGENT_TRACE", "1")
    monkeypatch.setenv("AGENT_TRACE_PATH", str(path))
    tr = start_run(user_id=1, domain="unified", question="charts?")
    assert tr is not None
    tr.selected_tools = ["list_vault_charts", "send_vault_charts"]
    tr.note_context(messages_chars=4000, tools_schema_chars=1200)
    tr.add_llm(
        iteration=0,
        latency_ms=10,
        model="deepseek-v4-flash",
        usage={"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050},
        tool_calls=1,
        context_chars=4000,
    )
    tr.add_tools(iteration=1, names=["list_vault_charts"])
    tr.add_llm(
        iteration=1,
        latency_ms=12,
        model="deepseek-v4-flash",
        usage=None,
        tool_calls=0,
        context_chars=8000,
    )
    tr.finish(reason="answer", answer="ok")
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["est_cost_usd"] > 0
    assert row["tool_calls_executed"] == 1
    assert row["context_chars_peak"] == 4000 or row["context_chars_peak"] >= 4000
    assert row["llm_rounds_count"] == 2
    # second round estimated from context
    assert row["llm_rounds"][1].get("tokens_estimated") is True
    assert int(row["llm_rounds"][1]["prompt_tokens"] or 0) > 0


def test_summarize_traces_daily(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    rows = [
        {
            "ts": "2026-08-01T10:00:00+00:00",
            "domain": "unified",
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "total_tokens": 1100,
            "est_cost_usd": 0.001,
            "total_latency_ms": 1000,
            "end_reason": "answer",
            "selected_tools": ["get_kanban"],
            "tool_iters": [{"iter": 1, "tools": ["get_kanban"]}],
            "llm_rounds": [{"prompt_tokens": 1000, "completion_tokens": 100}],
            "llm_rounds_count": 1,
            "rounds_missing_usage": 0,
            "context_chars_peak": 5000,
        },
        {
            "ts": "2026-08-02T10:00:00+00:00",
            "domain": "finance",
            "prompt_tokens": 2000,
            "completion_tokens": 50,
            "total_tokens": 2050,
            "est_cost_usd": 0.002,
            "total_latency_ms": 2000,
            "end_reason": "answer",
            "selected_tools": ["get_balance"],
            "tool_iters": [{"iter": 1, "tools": ["get_balance"]}],
            "llm_rounds": [{"prompt_tokens": 2000, "completion_tokens": 50}],
            "llm_rounds_count": 1,
            "rounds_missing_usage": 0,
            "context_chars_peak": 3000,
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    loaded = load_trace_rows(path, days=30)
    assert len(loaded) == 2
    s = summarize_traces(loaded, days=30)
    assert s.runs == 2
    assert s.total_tokens == 3150
    assert len(s.daily) == 2
    assert s.tool_calls_executed == 2
    assert s.as_dict()["usage_coverage_pct"] == 100.0
