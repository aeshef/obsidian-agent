#!/usr/bin/env python3
"""Score a labeled agent basket by expected_facts / forbidden_facts (no live LLM).

  PYTHONPATH=. ./scripts/oa-python.sh scripts/score_agent_basket.py \\
      --basket eval/gold/public_budget_quality_v0.yaml --only-frozen
  PYTHONPATH=. ./scripts/oa-python.sh scripts/score_agent_basket.py --only-labeled

Coverage = matched / len(expected_facts). Items with expect_fail: true must miss
or hit a forbidden fact (negative controls).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from shared.agent.fact_coverage import score_facts

ROOT = Path(__file__).resolve().parents[1]


def score_item(item: dict) -> dict:
    got = score_facts(
        str(item.get("answer") or ""),
        expected_facts=list(item.get("expected_facts") or []),
        forbidden_facts=list(item.get("forbidden_facts") or []),
    )
    return {
        "id": item.get("id"),
        "label": item.get("label"),
        "expect_fail": bool(item.get("expect_fail")),
        "coverage": got["coverage"],
        "hit": got["hit"],
        "miss": got["miss"],
        "forbidden_hit": got["forbidden_hit"],
        "answered": bool(item.get("answered") or item.get("answer")),
    }


def item_passes(row: dict) -> bool:
    """Positive items need full coverage and no forbidden hits; expect_fail inverts."""
    if row.get("expect_fail"):
        return bool(row.get("miss")) or bool(row.get("forbidden_hit"))
    cov_ok = row.get("coverage") is None or float(row["coverage"]) >= 1.0 - 1e-9
    return cov_ok and not row.get("forbidden_hit")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--basket",
        type=Path,
        default=ROOT / "eval" / "gold" / "public_budget_quality_v0.yaml",
    )
    ap.add_argument("--only-labeled", action="store_true")
    ap.add_argument("--only-frozen", action="store_true")
    ap.add_argument("--require-pass", action="store_true", help="exit 1 if any positive item fails")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.basket.is_file():
        print(f"missing basket: {args.basket}", file=sys.stderr)
        return 2
    doc = yaml.safe_load(args.basket.read_text(encoding="utf-8")) or {}
    items = list(doc.get("items") or [])
    if args.only_frozen:
        items = [i for i in items if str(i.get("label") or "") == "frozen"]
    elif args.only_labeled:
        items = [i for i in items if str(i.get("label") or "") in {"good", "bad", "ok", "frozen"}]
    rows = [score_item(i) for i in items if i.get("expected_facts") or i.get("forbidden_facts")]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        if not rows:
            print("no items with expected_facts/forbidden_facts")
            return 0
        for r in rows:
            cov = "n/a" if r["coverage"] is None else f"{r['coverage']:.0%}"
            ok = "PASS" if item_passes(r) else "FAIL"
            print(
                f"{ok} {r['label'] or '?':7} cov={cov:>4} miss={r['miss'][:3]} "
                f"forbid={r['forbidden_hit'][:2]} | {r['id']}"
            )
        with_cov = [r for r in rows if r["coverage"] is not None and not r.get("expect_fail")]
        if with_cov:
            avg = sum(r["coverage"] for r in with_cov) / len(with_cov)
            print(f"avg_coverage={avg:.2%} n={len(with_cov)}")
    if args.require_pass:
        fails = [r for r in rows if not item_passes(r)]
        if fails:
            print(f"{len(fails)} failing item(s)", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
