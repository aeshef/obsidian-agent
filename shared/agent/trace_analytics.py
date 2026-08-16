"""Aggregate agent_traces.jsonl into dashboard-ready metrics (no message bodies)."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from shared.agent.trace_cost import estimate_cost_usd, primary_model
from shared.domain_messages import dmsg


def parse_ts(raw: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return float(statistics.quantiles(values, n=100)[max(0, min(99, int(q) - 1))])


def load_trace_rows(path: Path, *, days: int | None = None) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    cutoff = None
    if days is not None and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if cutoff is not None:
                ts = parse_ts(row.get("ts"))
                if ts is not None and ts < cutoff:
                    continue
            rows.append(row)
    return rows


def _row_cost(row: dict[str, Any]) -> float:
    if row.get("est_cost_usd") is not None:
        try:
            return float(row["est_cost_usd"])
        except (TypeError, ValueError):
            pass
    model = str(row.get("model") or primary_model(row.get("llm_rounds") or []))
    return estimate_cost_usd(
        prompt_tokens=int(row.get("prompt_tokens") or 0),
        completion_tokens=int(row.get("completion_tokens") or 0),
        model=model,
    )


def _row_tools_executed(row: dict[str, Any]) -> int:
    if row.get("tool_calls_executed") is not None:
        return int(row.get("tool_calls_executed") or 0)
    return sum(len(it.get("tools") or []) for it in (row.get("tool_iters") or []))


@dataclass
class TraceSummary:
    days: int
    runs: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    est_cost_usd: float = 0.0
    tool_calls_executed: int = 0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_rounds: float = 0.0
    avg_selected_tools: float = 0.0
    avg_context_peak: float = 0.0
    rounds_missing_usage: int = 0
    llm_rounds_total: int = 0
    end_reasons: dict[str, int] = field(default_factory=dict)
    domains: dict[str, int] = field(default_factory=dict)
    top_tools: list[tuple[str, int]] = field(default_factory=list)
    daily: list[dict[str, Any]] = field(default_factory=list)
    domain_cost: list[tuple[str, float, int]] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "days": self.days,
            "runs": self.runs,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "est_cost_usd": round(self.est_cost_usd, 6),
            "tool_calls_executed": self.tool_calls_executed,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p50_latency_ms": round(self.p50_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "avg_rounds": round(self.avg_rounds, 2),
            "avg_selected_tools": round(self.avg_selected_tools, 2),
            "avg_context_peak": round(self.avg_context_peak, 1),
            "rounds_missing_usage": self.rounds_missing_usage,
            "llm_rounds_total": self.llm_rounds_total,
            "usage_coverage_pct": round(
                100.0
                * (1.0 - (self.rounds_missing_usage / self.llm_rounds_total))
                if self.llm_rounds_total
                else 100.0,
                1,
            ),
            "end_reasons": self.end_reasons,
            "domains": self.domains,
            "top_tools": self.top_tools,
            "daily": self.daily,
            "domain_cost": [
                {"domain": d, "est_cost_usd": c, "runs": n} for d, c, n in self.domain_cost
            ],
            "insights": self.insights,
        }


def summarize_traces(rows: list[dict[str, Any]], *, days: int) -> TraceSummary:
    s = TraceSummary(days=days)
    if not rows:
        s.insights.append(
            dmsg(
                "trace_insight_empty_window",
                default="No agent runs in the selected window — enable AGENT_TRACE=1.",
            )
        )
        return s

    latencies: list[float] = []
    rounds_list: list[int] = []
    selected_list: list[int] = []
    ctx_list: list[int] = []
    reasons: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    daily_tokens: dict[str, int] = defaultdict(int)
    daily_cost: dict[str, float] = defaultdict(float)
    daily_runs: dict[str, int] = defaultdict(int)
    daily_tools: dict[str, int] = defaultdict(int)
    domain_cost: dict[str, float] = defaultdict(float)
    domain_runs: dict[str, int] = defaultdict(int)

    for row in rows:
        s.runs += 1
        pt = int(row.get("prompt_tokens") or 0)
        ct = int(row.get("completion_tokens") or 0)
        s.prompt_tokens += pt
        s.completion_tokens += ct
        s.total_tokens += int(row.get("total_tokens") or (pt + ct))
        cost = _row_cost(row)
        s.est_cost_usd += cost
        tools_n = _row_tools_executed(row)
        s.tool_calls_executed += tools_n
        lat = float(row.get("total_latency_ms") or 0)
        latencies.append(lat)
        rounds = int(row.get("llm_rounds_count") or len(row.get("llm_rounds") or []))
        rounds_list.append(rounds)
        s.llm_rounds_total += rounds
        if row.get("rounds_missing_usage") is not None:
            s.rounds_missing_usage += int(row.get("rounds_missing_usage") or 0)
        else:
            # legacy rows: count null prompt_tokens
            s.rounds_missing_usage += sum(
                1
                for r in (row.get("llm_rounds") or [])
                if (r or {}).get("prompt_tokens") is None
            )
        selected_list.append(
            int(row.get("selected_tools_count") or len(row.get("selected_tools") or []))
        )
        ctx = int(row.get("context_chars_peak") or 0)
        if ctx:
            ctx_list.append(ctx)
        reasons[str(row.get("end_reason") or "?")] += 1
        dom = str(row.get("domain") or "?")
        domains[dom] += 1
        domain_cost[dom] += cost
        domain_runs[dom] += 1
        for name in row.get("selected_tools") or []:
            tools[str(name)] += 1
        for it in row.get("tool_iters") or []:
            for name in it.get("tools") or []:
                tools[str(name)] += 1

        ts = parse_ts(row.get("ts"))
        day = ts.date().isoformat() if ts else "unknown"
        daily_tokens[day] += int(row.get("total_tokens") or (pt + ct))
        daily_cost[day] += cost
        daily_runs[day] += 1
        daily_tools[day] += tools_n

    latencies.sort()
    s.avg_latency_ms = sum(latencies) / len(latencies)
    s.p50_latency_ms = statistics.median(latencies)
    s.p95_latency_ms = _pct(latencies, 95)
    s.avg_rounds = sum(rounds_list) / len(rounds_list)
    s.avg_selected_tools = sum(selected_list) / len(selected_list) if selected_list else 0
    s.avg_context_peak = sum(ctx_list) / len(ctx_list) if ctx_list else 0
    s.end_reasons = dict(reasons.most_common())
    s.domains = dict(domains.most_common())
    # Prefer executed-tool counts in top list: recount from tool_iters only for ranking
    exec_tools: Counter[str] = Counter()
    for row in rows:
        for it in row.get("tool_iters") or []:
            for name in it.get("tools") or []:
                exec_tools[str(name)] += 1
    s.top_tools = (exec_tools or tools).most_common(12)
    s.domain_cost = sorted(
        [(d, domain_cost[d], domain_runs[d]) for d in domain_cost],
        key=lambda x: -x[1],
    )
    days_sorted = sorted(d for d in daily_runs if d != "unknown")
    s.daily = [
        {
            "date": d,
            "runs": daily_runs[d],
            "tokens": daily_tokens[d],
            "est_cost_usd": round(daily_cost[d], 6),
            "tool_calls": daily_tools[d],
        }
        for d in days_sorted
    ]
    s.insights = _build_insights(s)
    return s


def _build_insights(s: TraceSummary) -> list[str]:
    out: list[str] = []
    if s.runs == 0:
        return [
            dmsg("trace_insight_no_data", default="No data."),
        ]
    cov = (
        100.0 * (1.0 - s.rounds_missing_usage / s.llm_rounds_total)
        if s.llm_rounds_total
        else 100.0
    )
    if cov < 85:
        out.append(
            dmsg(
                "trace_insight_usage_low",
                default=(
                    "Usage coverage {cov:.0f}% — streaming rounds may omit tokens; "
                    "dashboard estimates gaps from context size."
                ),
                cov=cov,
            )
        )
    else:
        out.append(
            dmsg(
                "trace_insight_usage_ok",
                default="Usage coverage {cov:.0f}% across {rounds} LLM rounds.",
                cov=cov,
                rounds=s.llm_rounds_total,
            )
        )
    if s.avg_rounds > 3.5:
        out.append(
            dmsg(
                "trace_insight_avg_rounds",
                default=(
                    "Avg {avg:.1f} LLM rounds per run — check extra tool loops "
                    "or tighten max_tool_calls."
                ),
                avg=s.avg_rounds,
            )
        )
    if s.avg_selected_tools > 10:
        out.append(
            dmsg(
                "trace_insight_avg_tools",
                default=(
                    "Avg {avg:.1f} tools selected per run — wide selection budget; "
                    "a smaller set cuts prompt tokens."
                ),
                avg=s.avg_selected_tools,
            )
        )
    budget = int(s.end_reasons.get("tool_budget") or 0)
    if budget:
        out.append(
            dmsg(
                "trace_insight_tool_budget",
                default="{n} run(s) hit tool_budget — answers may be truncated.",
                n=budget,
            )
        )
    if s.est_cost_usd > 0 and s.runs:
        out.append(
            dmsg(
                "trace_insight_cost",
                default="~${cost:.4f} estimate over {days}d (${per:.5f}/run).",
                cost=s.est_cost_usd,
                days=s.days,
                per=s.est_cost_usd / s.runs,
            )
        )
    if s.top_tools:
        name, n = s.top_tools[0]
        out.append(
            dmsg(
                "trace_insight_top_tool",
                default="Most frequent tool: {name} x{n}.",
                name=name,
                n=n,
            )
        )
    return out
