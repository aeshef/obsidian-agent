"""Align multiple day→value series on a shared ISO date grain (no domain hardcode)."""
from __future__ import annotations

import re

_LINE = re.compile(
    r"^\s*(20\d{2}-\d{2}-\d{2})\s*[|\t,;:]\s*(-?\d+(?:[.,]\d+)?)\s*$"
)
_LOOSE = re.compile(
    r"\b(20\d{2}-\d{2}-\d{2})\b[^\d\-]{0,12}(-?\d+(?:[.,]\d+)?)"
)


def parse_day_values(text: str) -> dict[str, float]:
    """Parse lines like ``YYYY-MM-DD|1234`` or loose ``YYYY-MM-DD … 1234``."""
    out: dict[str, float] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            m = _LOOSE.search(line)
        if not m:
            continue
        day, num = m.group(1), m.group(2).replace(",", ".")
        try:
            out[day] = float(num)
        except ValueError:
            continue
    return out


def align_day_series(
    series: dict[str, dict[str, float]],
    *,
    fill: float | None = None,
) -> list[tuple[str, dict[str, float]]]:
    """Outer-join series on ISO days. Missing values use ``fill`` or are omitted per label."""
    days: set[str] = set()
    for mapping in series.values():
        days.update(mapping.keys())
    rows: list[tuple[str, dict[str, float]]] = []
    for day in sorted(days):
        row: dict[str, float] = {}
        for label, mapping in series.items():
            if day in mapping:
                row[label] = mapping[day]
            elif fill is not None:
                row[label] = fill
        rows.append((day, row))
    return rows


def format_aligned(
    rows: list[tuple[str, dict[str, float]]],
    *,
    labels: list[str],
    limit: int = 60,
) -> str:
    if not rows:
        return ""
    header = "date | " + " | ".join(labels)
    lines = [header, "-" * min(80, len(header) + 8)]
    for day, row in rows[: max(1, limit)]:
        cells = []
        for lab in labels:
            if lab not in row:
                cells.append("-")
            else:
                v = row[lab]
                cells.append(f"{v:g}" if float(v).is_integer() else f"{v:.2f}")
        lines.append(f"{day} | " + " | ".join(cells))
    if len(rows) > limit:
        lines.append(f"... +{len(rows) - limit} more days")
    return "\n".join(lines)


def align_two_texts(
    text_a: str,
    text_b: str,
    *,
    label_a: str = "a",
    label_b: str = "b",
    fill_zero: bool = False,
    limit: int = 60,
) -> tuple[dict[str, dict[str, float]], str]:
    sa = parse_day_values(text_a)
    sb = parse_day_values(text_b)
    series = {label_a: sa, label_b: sb}
    rows = align_day_series(series, fill=0.0 if fill_zero else None)
    body = format_aligned(rows, labels=[label_a, label_b], limit=limit)
    meta = {
        "days": float(len(rows)),
        "a_points": float(len(sa)),
        "b_points": float(len(sb)),
        "shared": float(len(set(sa) & set(sb))),
    }
    return series, body + (
        f"\n# points a={int(meta['a_points'])} b={int(meta['b_points'])} "
        f"shared={int(meta['shared'])} union={int(meta['days'])}"
        if body
        else ""
    )
