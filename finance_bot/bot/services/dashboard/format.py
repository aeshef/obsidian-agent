"""Dashboard formatting helpers."""
from __future__ import annotations

from typing import Optional

from bot.dashboard_templates import dtpl
from shared.domain_messages import dmsg


def fmt_num(n: float, *, decimals: int = 0) -> str:
    s = f"{n:,.{decimals}f}".replace(",", " ")
    if decimals > 0 and "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def safe_comment(s: Optional[str], max_len: int = 50) -> str:
    """Table cell comment: no pipes/newlines, truncated."""
    if not s or not str(s).strip():
        return dtpl("misc", "dash")
    t = str(s).replace("|", " ").replace("\n", " ").strip()
    return (t[: max_len] + "…") if len(t) > max_len else t


def pie_with_pct(values_by_label: dict, *, limit: int = 10) -> list[tuple[str, float]]:
    """Return [(label_with_pct, value)] with percentage in label."""
    if not values_by_label:
        return []
    items = [(str(k), float(v)) for k, v in values_by_label.items() if float(v) > 0]
    if not items:
        return []
    items.sort(key=lambda x: -x[1])
    total = sum(v for _, v in items) or 1.0

    head = items[:limit]
    tail = items[limit:]

    out: list[tuple[str, float]] = []
    for label, val in head:
        pct = val / total * 100.0
        out.append((f"{label} — {fmt_num(val, decimals=0)} ({pct:.1f}%)", val))

    if tail:
        other_val = sum(v for _, v in tail)
        other_pct = other_val / total * 100.0
        # Not the misc category name — rolled-up tail below top-N
        out.append(
            (
                dmsg(
                    "finance",
                    "pie_other_categories",
                    amount=fmt_num(other_val, decimals=0),
                    pct=other_pct,
                ),
                other_val,
            )
        )

    return out
