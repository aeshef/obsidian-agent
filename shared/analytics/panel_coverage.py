"""Coverage statistics for the daily panel."""
from typing import Sequence
import numpy as np

def _col(rows: Sequence[dict], key: str) -> np.ndarray:
    out = []
    for r in rows:
        v = r.get(key)
        if v is None:
            out.append(np.nan)
        else:
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                out.append(np.nan)
    return np.asarray(out, dtype=float)


def panel_coverage(rows: Sequence[dict], metrics: Sequence[tuple[str, str]]) -> list[tuple[str, int, int]]:
    n = len(rows)
    out: list[tuple[str, int, int]] = []
    for key, label in metrics:
        cnt = int(np.isfinite(_col(rows, key)).sum())
        out.append((label, cnt, n))
    return out
