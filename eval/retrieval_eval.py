#!/usr/bin/env python3
"""Known-item retrieval eval for the knowledge-base RAG pipeline.

Methodology (fully automatic, no manual labeling):
  1. Sample N notes from the live index.
  2. For each note, an LLM writes ONE natural question the note answers
     (without quoting rare verbatim strings, to avoid trivial lexical match).
  3. Run production retrieval (`run_brain_query`): dense preselect → LLM select
     (catalog fallback if embeddings are not ready).
  4. Check whether the *source* note is recovered, and at which rank.

Reported metrics:
  - Preselect Recall  : source note survives stage-1 funnel
  - Select   Recall@1 : source note is the top selected note
  - Select   Recall@k : source note is anywhere in the selected set
  - MRR               : mean reciprocal rank over the selected set
  - Answer coverage   : share of queries that produced a grounded answer

Caveat (state this honestly in the pitch): known-item synthetic questions
give an *upper-bound-ish* estimate of retrieval quality; they are a baseline,
not a substitute for a human-labeled QA set. This harness is the scaffold to
grow that labeled set over time.

Usage:
    set -a && source .env && set +a          # load VAULT_PATH + DEEPSEEK_API_KEY
    export PYTHONPATH=.
    knowledge_bot/venv/bin/python eval/retrieval_eval.py --n 25 --seed 7
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path


def _die(msg: str) -> None:
    print(f"[eval] FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def _load_dotenv_if_present() -> None:
    """Best-effort .env load so the script works without pre-sourcing."""
    root = Path(__file__).resolve().parent.parent
    env = root / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


QUESTION_SYS = (
    "You generate ONE natural-language question that a specific personal note "
    "fully answers. Rules: write it the way the note's owner would ask months "
    "later from memory; do NOT copy rare verbatim phrases, IDs, or exact titles; "
    "keep it under 20 words; answer in the note's own language. "
    'Respond as JSON: {"question": "..."}.'
)


def _gen_question(llm, title: str, summary: str, preview: str) -> str:
    body = (summary or preview or "").strip()[:1500]
    user = f"TITLE: {title}\nCONTENT:\n{body}\n\nGenerate the question now."
    try:
        res = llm.chat_json(QUESTION_SYS, user, max_tokens=120)
        content = res.content if hasattr(res, "content") else res
        if isinstance(content, dict):
            q = content.get("question")
            if isinstance(q, str) and q.strip():
                return q.strip()
    except Exception as e:  # noqa: BLE001
        print(f"[eval] question-gen failed for {title!r}: {e}", file=sys.stderr)
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25, help="number of sampled notes")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--min-preview", type=int, default=400,
                    help="skip notes with body shorter than this")
    ap.add_argument("--out", default="eval/results.json")
    ap.add_argument("--no-chart", action="store_true")
    ap.add_argument(
        "--retrieve-only",
        action="store_true",
        help="skip answer LLM; score preselect/select paths only",
    )
    args = ap.parse_args()

    _load_dotenv_if_present()
    os.environ.setdefault("PYTHONPATH", ".")

    vault = os.environ.get("VAULT_PATH")
    if not vault:
        _die("VAULT_PATH is not set (source your .env first)")
    if not os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("DEEPSEEK_API_TOKEN"):
        _die("DEEPSEEK_API_KEY is not set (source your .env first)")
    vault_path = Path(vault).expanduser()
    if not vault_path.is_dir():
        _die(f"VAULT_PATH is not a directory: {vault_path}")

    # Imports after env is ready (they read config lazily).
    from knowledge_bot.core.llm import LLMClient
    from knowledge_bot.core.settings import get_config_path
    from knowledge_bot.services.query import brain_query
    from knowledge_bot.services.query.index_builder import (
        build_or_refresh_index,
        load_index,
    )

    print(f"[eval] building/loading index for {vault_path} ...")
    build_or_refresh_index(vault_path, force=False)
    idx = load_index()
    all_entries = idx.get("entries") or []
    corpus_total = idx.get("count") or len(all_entries)

    # The production preselect runs over a single compact catalog that is capped
    # by context size (KNOWLEDGE_COMPACT_CATALOG_MAX_CHARS). Notes beyond that cap
    # are simply not searchable in one shot, so sampling them would measure the
    # context cap, not retriever quality. We evaluate retriever quality on the
    # *searchable window* and report corpus coverage separately (honest split).
    from knowledge_bot.services.query.brain_query import _build_compact_catalog
    _, short_to_full = _build_compact_catalog(all_entries)
    in_window = set(short_to_full.values())
    window_size = len(in_window)
    window_coverage = round(window_size / corpus_total, 3) if corpus_total else 0.0

    eligible = [e for e in all_entries
                if e.get("rel_path") in in_window
                and len((e.get("preview") or "")) >= args.min_preview]
    if len(eligible) < args.n:
        print(f"[eval] only {len(eligible)} eligible in-window notes, using all")
        sample = eligible
    else:
        random.seed(args.seed)
        sample = random.sample(eligible, args.n)
    print(f"[eval] corpus={corpus_total} notes; searchable window={window_size} "
          f"({window_coverage:.0%}); evaluating on {len(sample)} in-window notes")

    llm = LLMClient()
    config_path = get_config_path()

    records = []
    t0 = time.time()
    for i, note in enumerate(sample, 1):
            src = note["rel_path"]
            title = note.get("title") or Path(src).stem
            q = _gen_question(llm, title, note.get("summary", ""), note.get("preview", ""))
            if not q:
                records.append({"src": src, "skipped": True})
                print(f"[{i}/{len(sample)}] SKIP (no question) {title}")
                continue

            uid = 900000 + i  # unique id -> no cross-query history bias
            try:
                res = brain_query.run_brain_query(
                    vault_path,
                    config_path,
                    llm,
                    uid,
                    q,
                    retrieve_only=args.retrieve_only,
                    update_stats=False,
                )
                answered = bool(res.ok and res.text and len(res.text) > 40)
                if args.retrieve_only:
                    answered = bool(res.ok and res.selected_paths)
            except Exception as e:  # noqa: BLE001
                print(f"[{i}] run_brain_query error: {e}", file=sys.stderr)
                answered = False
                res = None

            pre = list(res.preselect_paths) if res else []
            final = list(res.selected_paths) if res else []
            rank = (final.index(src) + 1) if src in final else 0
            rec = {
                "src": src,
                "question": q,
                "in_preselect": src in pre,
                "in_select": src in final,
                "rank": rank,
                "n_selected": len(final),
                "answered": answered,
                "ok": bool(res.ok) if res else False,
            }
            records.append(rec)
            flag = f"rank={rank}" if rank else ("pre-only" if rec["in_preselect"] else "MISS")
            print(f"[{i}/{len(sample)}] {flag:>9}  {title[:48]!r}")

    scored = [r for r in records if not r.get("skipped")]
    n = len(scored) or 1
    pre_recall = sum(r["in_preselect"] for r in scored) / n
    sel_recall = sum(r["in_select"] for r in scored) / n
    recall_at_1 = sum(r["rank"] == 1 for r in scored) / n
    mrr = sum((1.0 / r["rank"]) for r in scored if r["rank"]) / n
    coverage = sum(r["answered"] for r in scored) / n
    avg_sel = sum(r["n_selected"] for r in scored) / n

    summary = {
        "corpus_notes": corpus_total,
        "searchable_window": window_size,
        "window_coverage": window_coverage,
        "evaluated_in_window": len(scored),
        "skipped": len(records) - len(scored),
        "preselect_recall": round(pre_recall, 3),
        "select_recall_at_k": round(sel_recall, 3),
        "select_recall_at_1": round(recall_at_1, 3),
        "mrr": round(mrr, 3),
        "answer_coverage": round(coverage, 3),
        "avg_selected_notes": round(avg_sel, 2),
        "elapsed_sec": round(time.time() - t0, 1),
        "seed": args.seed,
    }

    out = {"summary": summary, "records": records}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== RETRIEVAL EVAL SUMMARY =====")
    for k, v in summary.items():
        print(f"  {k:24}: {v}")
    print(f"\n[eval] wrote {out_path}")

    if not args.no_chart:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            labels = ["Preselect\nRecall", "Select\nRecall@k", "Select\nRecall@1",
                      "MRR", "Answer\ncoverage"]
            vals = [pre_recall, sel_recall, recall_at_1, mrr, coverage]
            fig, ax = plt.subplots(figsize=(7, 4))
            bars = ax.bar(labels, vals, color="#7c3aed")
            ax.set_ylim(0, 1.05)
            ax.set_ylabel("score")
            ax.set_title(f"KB retrieval — known-item eval (n={len(scored)} in-window; "
                         f"corpus={corpus_total}, window={window_size})")
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 0.02,
                        f"{v:.2f}", ha="center", fontsize=10)
            fig.tight_layout()
            chart = out_path.with_suffix(".png")
            fig.savefig(chart, dpi=150)
            print(f"[eval] wrote chart {chart}")
        except Exception as e:  # noqa: BLE001
            print(f"[eval] chart skipped: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
