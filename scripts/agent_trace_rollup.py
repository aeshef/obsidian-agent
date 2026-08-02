#!/usr/bin/env python3
"""Roll up agent_traces.jsonl into a short ops summary (no message bodies / PII content).

Usage:
  PYTHONPATH=. python scripts/agent_trace_rollup.py
  PYTHONPATH=. python scripts/agent_trace_rollup.py --path logs/agent_traces.jsonl --days 7
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _parse_ts(raw: str) -> datetime | None:
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Summarize agent trace jsonl")
    p.add_argument("--path", type=Path, default=None)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args(argv)

    path = args.path
    if path is None:
        root = Path(__file__).resolve().parents[1]
        path = root / "logs" / "agent_traces.jsonl"
    if not path.is_file():
        print(f"no traces: {path}", file=sys.stderr)
        return 1

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, args.days))
    latencies: list[float] = []
    tokens = 0
    reasons: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    n = 0

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(str(row.get("ts") or ""))
            if ts is not None and ts < cutoff:
                continue
            n += 1
            latencies.append(float(row.get("total_latency_ms") or 0))
            tokens += int(row.get("total_tokens") or 0)
            reasons[str(row.get("end_reason") or "?")] += 1
            domains[str(row.get("domain") or "?")] += 1
            for name in row.get("selected_tools") or []:
                tools[str(name)] += 1
            for it in row.get("tool_iters") or []:
                for name in it.get("tools") or []:
                    tools[str(name)] += 1

    if n == 0:
        print(f"no rows in last {args.days}d ({path})")
        return 0

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = _pct(latencies, 95)
    print(f"runs={n} days={args.days} tokens={tokens}")
    print(f"latency_ms p50={p50:.0f} p95={p95:.0f} max={max(latencies):.0f}")
    print("end_reason:", ", ".join(f"{k}={v}" for k, v in reasons.most_common()))
    print("domain:", ", ".join(f"{k}={v}" for k, v in domains.most_common()))
    print("top_tools:", ", ".join(f"{k}={v}" for k, v in tools.most_common(12)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
