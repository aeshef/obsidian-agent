from __future__ import annotations

from typing import Any, Sequence


def ranks_for(paths: Sequence[str], relevant: Sequence[str]) -> list[int]:
    rel = [p for p in relevant if p]
    out: list[int] = []
    for gold in rel:
        try:
            out.append(list(paths).index(gold) + 1)
        except ValueError:
            out.append(0)
    return out


def recall_at_k(paths: Sequence[str], relevant: Sequence[str], k: int) -> float:
    rel = [p for p in relevant if p]
    if not rel:
        return 0.0
    top = set(list(paths)[:k])
    return sum(1 for p in rel if p in top) / len(rel)


def hit_at_k(paths: Sequence[str], relevant: Sequence[str], k: int) -> bool:
    rel = [p for p in relevant if p]
    if not rel:
        return False
    top = set(list(paths)[:k])
    return any(p in top for p in rel)


def mrr_for(paths: Sequence[str], relevant: Sequence[str]) -> float:
    rel = [p for p in relevant if p]
    if not rel:
        return 0.0
    best = 0.0
    for gold in rel:
        try:
            rank = list(paths).index(gold) + 1
        except ValueError:
            continue
        best = max(best, 1.0 / rank)
    return best


def summarize_records(records: list[dict[str, Any]], *, k: int = 14) -> dict[str, Any]:
    scored = [r for r in records if not r.get("skipped")]
    n = len(scored) or 1
    return {
        "n": len(scored),
        "skipped": sum(1 for r in records if r.get("skipped")),
        "recall_at_k": round(sum(r.get("hit_k", 0) for r in scored) / n, 3),
        "recall_at_5": round(sum(r.get("hit_5", 0) for r in scored) / n, 3),
        "recall_at_1": round(sum(r.get("rank") == 1 for r in scored) / n, 3),
        "mrr": round(sum(float(r.get("mrr") or 0) for r in scored) / n, 3),
        "select_k": k,
        "by_bucket": _by_bucket(scored, k),
    }


def _by_bucket(scored: list[dict[str, Any]], k: int) -> dict[str, dict[str, float]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in scored:
        buckets.setdefault(str(r.get("bucket") or "all"), []).append(r)
    out: dict[str, dict[str, float]] = {}
    for name, rows in sorted(buckets.items()):
        m = len(rows) or 1
        out[name] = {
            "n": len(rows),
            "recall_at_k": round(sum(r.get("hit_k", 0) for r in rows) / m, 3),
            "mrr": round(sum(float(r.get("mrr") or 0) for r in rows) / m, 3),
        }
    return out


def score_query(
    paths: Sequence[str],
    relevant: Sequence[str],
    *,
    k: int = 14,
) -> dict[str, Any]:
    rank_list = ranks_for(paths, relevant)
    rank = min((x for x in rank_list if x), default=0)
    return {
        "rank": rank,
        "ranks": rank_list,
        "n_selected": len(list(paths)[:k]),
        "hit_k": int(hit_at_k(paths, relevant, k)),
        "hit_5": int(hit_at_k(paths, relevant, 5)),
        "mrr": round(mrr_for(paths, relevant), 4),
        "paths": list(paths)[:k],
    }
