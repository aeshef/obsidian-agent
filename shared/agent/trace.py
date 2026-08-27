"""Structured agent-run traces (cost/latency) — jsonl, no tool bodies / PII content."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.agent.trace_cost import (
    estimate_cost_usd,
    estimate_tokens_from_chars,
    primary_model,
)

log = logging.getLogger("shared.agent.trace")


def _enabled() -> bool:
    env = (os.environ.get("AGENT_TRACE") or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        from shared.agent.platform_config import platform_int

        return bool(platform_int("agent_trace", "enabled", default=0))
    except Exception:
        return False


def _trace_path() -> Path:
    env = (os.environ.get("AGENT_TRACE_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    try:
        from shared.agent.platform_config import platform_value

        raw = platform_value("agent_trace", "path", default="")
        if raw:
            return Path(str(raw)).expanduser()
    except Exception:
        pass
    root = (os.environ.get("AGENT_ROOT") or "").strip()
    base = Path(root) if root else Path.cwd()
    return base / "logs" / "agent_traces.jsonl"


@dataclass
class AgentRunTrace:
    user_id: int
    domain: str
    question_chars: int
    started_mono: float = field(default_factory=time.perf_counter)
    started_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    llm_rounds: list[dict[str, Any]] = field(default_factory=list)
    tool_iters: list[dict[str, Any]] = field(default_factory=list)
    selected_tools: list[str] = field(default_factory=list)
    end_reason: str = ""
    answer_chars: int = 0
    # Context / schema sizes observed before each LLM call (chars).
    context_chars_iters: list[int] = field(default_factory=list)
    tools_schema_chars: int = 0
    tool_clips: list[dict[str, Any]] = field(default_factory=list)
    cascade_escalate_reasons: list[str] = field(default_factory=list)
    verify_ok: bool | None = None
    verify_rewrote: bool | None = None
    session_messages: int = 0
    working_set_items: int = 0
    core_priors_lines: int = 0

    def note_context(self, *, messages_chars: int, tools_schema_chars: int = 0) -> None:
        self.context_chars_iters.append(int(messages_chars))
        if tools_schema_chars:
            self.tools_schema_chars = max(self.tools_schema_chars, int(tools_schema_chars))

    def note_memory_sizes(
        self,
        *,
        session_messages: int = 0,
        working_set_items: int = 0,
        core_priors_lines: int = 0,
    ) -> None:
        self.session_messages = max(0, int(session_messages or 0))
        self.working_set_items = max(0, int(working_set_items or 0))
        self.core_priors_lines = max(0, int(core_priors_lines or 0))

    def note_tool_clip(self, *, tool: str, stats: dict[str, Any]) -> None:
        row = {"tool": str(tool or ""), **dict(stats or {})}
        self.tool_clips.append(row)

    def note_cascade(self, reason: str) -> None:
        r = str(reason or "").strip()
        if r:
            self.cascade_escalate_reasons.append(r)

    def note_verify(self, *, ok: bool, rewrote: bool) -> None:
        self.verify_ok = bool(ok)
        self.verify_rewrote = bool(rewrote)

    def add_llm(
        self,
        *,
        iteration: int,
        latency_ms: float,
        model: str = "",
        usage: dict[str, Any] | None = None,
        tool_calls: int = 0,
        context_chars: int | None = None,
    ) -> None:
        u = usage or {}
        prompt = u.get("prompt_tokens")
        completion = u.get("completion_tokens")
        total = u.get("total_tokens")
        estimated = False
        if prompt is None and context_chars is not None and context_chars > 0:
            prompt = estimate_tokens_from_chars(context_chars + self.tools_schema_chars)
            estimated = True
        row = {
            "iter": iteration,
            "latency_ms": round(latency_ms, 1),
            "model": model,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total
            if total is not None
            else (
                (int(prompt or 0) + int(completion or 0))
                if prompt is not None or completion is not None
                else None
            ),
            "tool_calls": tool_calls,
            "tokens_estimated": estimated,
        }
        if context_chars is not None:
            row["context_chars"] = int(context_chars)
        self.llm_rounds.append(row)

    def add_tools(self, *, iteration: int, names: list[str]) -> None:
        self.tool_iters.append({"iter": iteration, "tools": list(names)})

    def finish(self, *, reason: str, answer: str = "") -> None:
        self.end_reason = reason
        self.answer_chars = len(answer or "")
        if not _enabled():
            return
        total_ms = (time.perf_counter() - self.started_mono) * 1000.0
        prompt_tokens = sum(int(r.get("prompt_tokens") or 0) for r in self.llm_rounds)
        completion_tokens = sum(
            int(r.get("completion_tokens") or 0) for r in self.llm_rounds
        )
        tool_calls_requested = sum(int(r.get("tool_calls") or 0) for r in self.llm_rounds)
        tool_calls_executed = sum(
            len(it.get("tools") or []) for it in self.tool_iters
        )
        model = primary_model(self.llm_rounds)
        rounds_missing_usage = sum(
            1 for r in self.llm_rounds if r.get("prompt_tokens") is None
        )
        rounds_estimated = sum(1 for r in self.llm_rounds if r.get("tokens_estimated"))
        cost = estimate_cost_usd(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
        )
        ctx_peak = max(self.context_chars_iters) if self.context_chars_iters else 0
        clip_n = len(self.tool_clips)
        clipped_n = sum(1 for c in self.tool_clips if c.get("clipped"))
        raw_sum = sum(int(c.get("raw_chars") or 0) for c in self.tool_clips)
        llm_sum = sum(int(c.get("llm_chars") or 0) for c in self.tool_clips)
        clip_ratio = (1.0 - (llm_sum / raw_sum)) if raw_sum > 0 else 0.0
        payload = {
            "ts": self.started_iso,
            "user_id": self.user_id,
            "domain": self.domain,
            "question_chars": self.question_chars,
            "answer_chars": self.answer_chars,
            "end_reason": self.end_reason,
            "total_latency_ms": round(total_ms, 1),
            "model": model,
            "selected_tools": self.selected_tools,
            "selected_tools_count": len(self.selected_tools),
            "llm_rounds": self.llm_rounds,
            "llm_rounds_count": len(self.llm_rounds),
            "tool_iters": self.tool_iters,
            "tool_calls_requested": tool_calls_requested,
            "tool_calls_executed": tool_calls_executed,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "est_cost_usd": round(cost, 6),
            "context_chars_peak": ctx_peak,
            "tools_schema_chars": self.tools_schema_chars,
            "rounds_missing_usage": rounds_missing_usage,
            "rounds_tokens_estimated": rounds_estimated,
            "tool_clip_count": clip_n,
            "tool_clipped_count": clipped_n,
            "tool_clip_ratio": round(clip_ratio, 4),
            "tool_raw_chars_sum": raw_sum,
            "tool_llm_chars_sum": llm_sum,
            "cascade_escalate_reasons": list(self.cascade_escalate_reasons),
            "verify_ok": self.verify_ok,
            "verify_rewrote": self.verify_rewrote,
            "session_messages": self.session_messages,
            "working_set_items": self.working_set_items,
            "core_priors_lines": self.core_priors_lines,
        }
        path = _trace_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(payload, ensure_ascii=False)
            with _LOCK:
                with path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except OSError as e:
            log.warning("agent trace write failed: %s", e)


_LOCK = threading.Lock()


def start_run(*, user_id: int, domain: str, question: str) -> AgentRunTrace | None:
    if not _enabled():
        return None
    return AgentRunTrace(
        user_id=int(user_id),
        domain=str(domain or ""),
        question_chars=len(question or ""),
    )
