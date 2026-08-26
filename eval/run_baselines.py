#!/usr/bin/env python3
"""Blind retrieval baselines: production dense vs optional LLM-catalog.

  PYTHONPATH=. python eval/run_baselines.py \
      --gold eval/gold/public_v0.yaml --retrievers dense,catalog
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_dotenv() -> None:
    env = _ROOT / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _entries() -> tuple[list[dict[str, Any]], float]:
    from knowledge_bot.services.query.index_builder import build_or_refresh_index, load_index

    vault = os.environ.get("VAULT_PATH")
    if not vault:
        raise SystemExit("VAULT_PATH is not set")
    vault_path = Path(vault).expanduser()
    build_or_refresh_index(vault_path, force=False)
    idx = load_index()
    return list(idx.get("entries") or []), float(idx.get("generated_at") or 0)


def _catalog_retriever(k: int) -> Callable[[str], list[str]]:
    from knowledge_bot.core.llm import LLMClient
    from knowledge_bot.core.settings import get_config_path
    from knowledge_bot.services.query.brain_query import run_brain_query

    vault = Path(os.environ["VAULT_PATH"]).expanduser()
    cfg = get_config_path()
    llm = LLMClient()
    n = {"i": 0}

    def search(question: str) -> list[str]:
        n["i"] += 1
        uid = 910000 + n["i"]
        prev = os.environ.get("KNOWLEDGE_PRESELECT_BACKEND")
        os.environ["KNOWLEDGE_PRESELECT_BACKEND"] = "catalog"
        try:
            res = run_brain_query(
                vault,
                cfg,
                llm,
                uid,
                question,
                retrieve_only=True,
                update_stats=False,
            )
        finally:
            if prev is None:
                os.environ.pop("KNOWLEDGE_PRESELECT_BACKEND", None)
            else:
                os.environ["KNOWLEDGE_PRESELECT_BACKEND"] = prev
        return list(res.selected_paths)[:k]

    return search


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True, type=Path)
    ap.add_argument(
        "--retrievers",
        default="dense",
        help="comma list: dense,catalog",
    )
    ap.add_argument("--out-dir", type=Path, default=_ROOT / "eval" / "runs")
    args = ap.parse_args()

    _load_dotenv()
    from eval.retrieval.gold import load_gold
    from eval.retrieval.metrics import score_query, summarize_records
    from shared.agent.platform_config import platform_int

    gold = load_gold(args.gold)
    if not gold:
        print(f"[eval] no labeled queries in {args.gold}", file=sys.stderr)
        return 1

    k = platform_int(
        "knowledge_query", "max_selected_notes", env="KNOWLEDGE_MAX_SELECTED_NOTES", default=14
    )
    entries, _stamp = _entries()
    names = [x.strip() for x in args.retrievers.split(",") if x.strip()]

    retrievers: dict[str, Callable[[str], list[str]]] = {}
    if "dense" in names:
        from knowledge_bot.services.query.dense_index import search_notes

        retrievers["dense"] = lambda q, ents=entries: search_notes(q, ents, top_n=k)
    if "catalog" in names:
        retrievers["catalog"] = _catalog_retriever(k)

    if not retrievers:
        print("[eval] no retrievers available", file=sys.stderr)
        return 1

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "gold": str(args.gold),
        "n_queries": len(gold),
        "corpus": len(entries),
        "retrievers": {},
    }

    for name, fn in retrievers.items():
        t0 = time.time()
        records = []
        for row in gold:
            paths = fn(row["query"])
            if not row["relevant_paths"]:
                records.append(
                    {
                        **row,
                        "skipped": True,
                        "rank": 0,
                        "hit_k": 0,
                        "hit_5": 0,
                        "mrr": 0.0,
                        "paths": paths,
                    }
                )
                print(f"[{name}] skip-refuse  {row['id']}")
                continue
            scored = score_query(paths, row["relevant_paths"], k=k)
            records.append({**row, **scored})
            flag = f"rank={scored['rank']}" if scored["rank"] else "MISS"
            print(f"[{name}] {flag:>9}  {row['id']}  {row['query'][:60]!r}")
        summary = summarize_records(records, k=k)
        summary["elapsed_sec"] = round(time.time() - t0, 1)
        report["retrievers"][name] = {"summary": summary, "records": records}
        print(f"===== {name} =====")
        for key, val in summary.items():
            print(f"  {key:16}: {val}")

    out_path = out_dir / "baselines.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = args.out_dir / "latest.json"
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[eval] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
