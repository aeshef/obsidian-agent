#!/usr/bin/env python3
"""Score a labeled agent basket by expected_facts / forbidden_facts (no live LLM).

  PYTHONPATH=. ./scripts/oa-python.sh scripts/score_agent_basket.py
  PYTHONPATH=. ./scripts/oa-python.sh scripts/score_agent_basket.py \\
      --basket eval/gold/local_basket.yaml --only-labeled

For each item with label in {good,bad,ok} and expected_facts:
  coverage = matched / len(expected_facts)
  For label=good expect high coverage; for label=bad expect misses on critical facts
  when ``expect_fail: true`` (optional).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _norm(s: str) -> str:
    return " ".join((s or "").casefold().split())


def score_item(item: dict) -> dict:
    answer = _norm(str(item.get("answer") or ""))
    expected = [str(x) for x in (item.get("expected_facts") or []) if str(x).strip()]
    forbidden = [str(x) for x in (item.get("forbidden_facts") or []) if str(x).strip()]
    hit = [f for f in expected if _norm(f) in answer]
    miss = [f for f in expected if _norm(f) not in answer]
    bad_hit = [f for f in forbidden if _norm(f) in answer]
    cov = (len(hit) / len(expected)) if expected else None
    return {
        "id": item.get("id"),
        "label": item.get("label"),
        "coverage": cov,
        "hit": hit,
        "miss": miss,
        "forbidden_hit": bad_hit,
        "answered": bool(item.get("answered")),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--basket",
        type=Path,
        default=ROOT / "eval" / "gold" / "local_basket.yaml",
    )
    ap.add_argument("--only-labeled", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.basket.is_file():
        print(f"missing basket: {args.basket}", file=sys.stderr)
        return 2
    doc = yaml.safe_load(args.basket.read_text(encoding="utf-8")) or {}
    items = list(doc.get("items") or [])
    if args.only_labeled:
        items = [i for i in items if str(i.get("label") or "") in {"good", "bad", "ok"}]
    rows = [score_item(i) for i in items if i.get("expected_facts") or i.get("forbidden_facts")]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("no items with expected_facts/forbidden_facts")
        return 0
    for r in rows:
        cov = "n/a" if r["coverage"] is None else f"{r['coverage']:.0%}"
        print(
            f"{r['label'] or '?':5} cov={cov:>4} miss={r['miss'][:3]} "
            f"forbid={r['forbidden_hit'][:2]} | {r['id']}"
        )
    with_cov = [r for r in rows if r["coverage"] is not None]
    if with_cov:
        avg = sum(r["coverage"] for r in with_cov) / len(with_cov)
        print(f"avg_coverage={avg:.2%} n={len(with_cov)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
