#!/usr/bin/env python3
"""Suggest D+G budget knobs from agent_traces (Pareto-ish, no LLM).

Reads logs/agent_traces.jsonl (or --traces PATH) and prints:
  - clip_ratio by tool / overall
  - end_reason rates (max_iters, tool_budget)
  - recommended tool_result_max_chars from p95(tool_raw_chars) * headroom

  PYTHONPATH=. ./scripts/oa-python.sh scripts/sweep_budget_pareto.py
  PYTHONPATH=. ./scripts/oa-python.sh scripts/sweep_budget_pareto.py --days 21
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parse_ts(row: dict) -> datetime | None:
    raw = row.get("ts") or row.get("started_at") or row.get("t")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _quantile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    if len(ys) == 1:
        return float(ys[0])
    idx = min(len(ys) - 1, max(0, int(round((len(ys) - 1) * q))))
    return float(ys[idx])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--traces",
        type=Path,
        default=ROOT / "logs" / "agent_traces.jsonl",
    )
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--headroom", type=float, default=1.2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.traces.is_file():
        print(f"no traces at {args.traces} — run the agent first", file=sys.stderr)
        return 1

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, args.days))
    rows: list[dict] = []
    with args.traces.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(row)
            if ts is not None and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts is not None and ts < cutoff:
                continue
            rows.append(row)

    if not rows:
        print("no rows in window", file=sys.stderr)
        return 1

    end_reasons = Counter(str(r.get("end_reason") or "?") for r in rows)
    clips = [float(r["tool_clip_ratio"]) for r in rows if r.get("tool_clip_ratio") is not None]
    raw_sums = [float(r["tool_raw_chars_sum"]) for r in rows if r.get("tool_raw_chars_sum")]
    by_tool_raw: dict[str, list[float]] = defaultdict(list)
    by_tool_clip: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        for clip in r.get("tool_clips") or []:
            name = str(clip.get("tool") or "?")
            raw = clip.get("raw_chars")
            llm = clip.get("llm_chars")
            if raw is not None:
                by_tool_raw[name].append(float(raw))
            if raw and llm is not None and float(raw) > 0:
                by_tool_clip[name].append(1.0 - float(llm) / float(raw))

    from shared.agent.budget_caps import recommend_cap, tool_result_max_chars

    p95_raw = _quantile(raw_sums, 0.95) if raw_sums else 0.0
    rec = recommend_cap(
        [int(x) for x in raw_sums] if raw_sums else [tool_result_max_chars()],
        q=0.95,
        headroom=args.headroom,
    )
    n = len(rows)
    report = {
        "n_runs": n,
        "days": args.days,
        "end_reason_rates": {k: round(v / n, 4) for k, v in sorted(end_reasons.items())},
        "avg_clip_ratio": round(sum(clips) / len(clips), 4) if clips else 0.0,
        "p95_tool_raw_chars_sum": int(p95_raw),
        "current_tool_result_max_chars": tool_result_max_chars(),
        "recommended_tool_result_max_chars": rec,
        "tools": {
            name: {
                "n": len(by_tool_raw[name]),
                "p95_raw": int(_quantile(by_tool_raw[name], 0.95)),
                "avg_clip": round(
                    sum(by_tool_clip.get(name) or [0.0]) / max(1, len(by_tool_clip.get(name) or [])),
                    4,
                ),
            }
            for name in sorted(by_tool_raw.keys())
        },
        "actions": [],
    }
    if report["avg_clip_ratio"] > 0.05:
        report["actions"].append(
            "clip_ratio elevated → raise tool_result_max_chars or use summary=unique dumps"
        )
    if report["end_reason_rates"].get("max_iters", 0) > 0.05:
        report["actions"].append("max_iters rate >5% → raise agent.max_iters or fix tool-select")
    if report["end_reason_rates"].get("tool_budget", 0) > 0.05:
        report["actions"].append("tool_budget rate >5% → raise agent.max_tool_calls")
    if rec > tool_result_max_chars():
        report["actions"].append(
            f"set agent.tool_result_max_chars ≥ {rec} (p95 raw × {args.headroom})"
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"runs={n} days={args.days} avg_clip={report['avg_clip_ratio']}")
    print("end_reasons:", report["end_reason_rates"])
    print(
        f"tool_result_max_chars current={report['current_tool_result_max_chars']} "
        f"recommended={rec} (p95_raw_sum={int(p95_raw)})"
    )
    for name, info in list(report["tools"].items())[:12]:
        print(f"  {name}: n={info['n']} p95_raw={info['p95_raw']} avg_clip={info['avg_clip']}")
    for a in report["actions"]:
        print(f"→ {a}")
    if not report["actions"]:
        print("→ no D/G bump suggested from this window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
