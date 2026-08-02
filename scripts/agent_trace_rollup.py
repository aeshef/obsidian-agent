#!/usr/bin/env python3
"""Roll up agent_traces.jsonl into a short ops summary (no message bodies / PII).

Usage:
  PYTHONPATH=. python scripts/agent_trace_rollup.py
  PYTHONPATH=. python scripts/agent_trace_rollup.py --path logs/agent_traces.jsonl --days 7
  PYTHONPATH=. python scripts/agent_trace_rollup.py --days 14 --json
  PYTHONPATH=. python scripts/agent_trace_rollup.py --days 14 --dashboard
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Summarize agent trace jsonl")
    p.add_argument("--path", type=Path, default=None)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--json", action="store_true", help="Print full summary JSON")
    p.add_argument(
        "--dashboard",
        action="store_true",
        help="Also build Obsidian cost dashboard (build_agent_cost_dashboard.py)",
    )
    args = p.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from shared.agent.trace_analytics import load_trace_rows, summarize_traces

    path = args.path
    if path is None:
        path = root / "logs" / "agent_traces.jsonl"
    if not path.is_file():
        print(f"no traces: {path}", file=sys.stderr)
        return 1

    rows = load_trace_rows(path, days=args.days)
    summary = summarize_traces(rows, days=args.days)
    d = summary.as_dict()

    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print(
            f"runs={d['runs']} days={d['days']} tokens={d['total_tokens']} "
            f"est_usd={d['est_cost_usd']:.4f} tools={d['tool_calls_executed']}"
        )
        print(
            f"latency_ms p50={d['p50_latency_ms']:.0f} p95={d['p95_latency_ms']:.0f} "
            f"avg_rounds={d['avg_rounds']:.2f} usage_coverage={d['usage_coverage_pct']:.1f}%"
        )
        print(
            "end_reason:",
            ", ".join(f"{k}={v}" for k, v in (d.get("end_reasons") or {}).items()) or "-",
        )
        print(
            "domain:",
            ", ".join(f"{k}={v}" for k, v in (d.get("domains") or {}).items()) or "-",
        )
        print(
            "top_tools:",
            ", ".join(f"{k}={v}" for k, v in (d.get("top_tools") or [])[:12]) or "-",
        )
        for tip in d.get("insights") or []:
            print(f"- {tip}")

    if args.dashboard:
        import importlib.util

        dash_path = root / "scripts" / "build_agent_cost_dashboard.py"
        spec = importlib.util.spec_from_file_location("build_agent_cost_dashboard", dash_path)
        if spec is None or spec.loader is None:
            print(f"cannot load {dash_path}", file=sys.stderr)
            return 1
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return int(mod.main(["--path", str(path), "--days", str(args.days)]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
