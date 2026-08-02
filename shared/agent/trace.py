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

    def add_llm(
        self,
        *,
        iteration: int,
        latency_ms: float,
        model: str = "",
        usage: dict[str, Any] | None = None,
        tool_calls: int = 0,
    ) -> None:
        u = usage or {}
        self.llm_rounds.append(
            {
                "iter": iteration,
                "latency_ms": round(latency_ms, 1),
                "model": model,
                "prompt_tokens": u.get("prompt_tokens"),
                "completion_tokens": u.get("completion_tokens"),
                "total_tokens": u.get("total_tokens"),
                "tool_calls": tool_calls,
            }
        )

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
        payload = {
            "ts": self.started_iso,
            "user_id": self.user_id,
            "domain": self.domain,
            "question_chars": self.question_chars,
            "answer_chars": self.answer_chars,
            "end_reason": self.end_reason,
            "total_latency_ms": round(total_ms, 1),
            "selected_tools": self.selected_tools,
            "llm_rounds": self.llm_rounds,
            "tool_iters": self.tool_iters,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
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
