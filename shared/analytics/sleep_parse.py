"""Parse iPhone Health sleep_detail multiline blocks."""
from __future__ import annotations

import re
from typing import Any

_STAGE_KEYS = (
    ("Deep", "iphone_sleep_deep_min"),
    ("REM", "iphone_sleep_rem_min"),
    ("Core", "iphone_sleep_core_min"),
    ("Awake", "iphone_sleep_awake_min"),
)


def parse_sleep_detail(sleep_detail: str | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not sleep_detail:
        return out
    m = re.search(r"Total Time Asleep:\s*(\d+)\s*hours?\s*(\d+)?", sleep_detail)
    if m:
        out["iphone_sleep_hours"] = int(m.group(1)) + int(m.group(2) or 0) / 60.0
    for stage, key in _STAGE_KEYS:
        m = re.search(rf"{stage} for (\d+) hours? and (\d+) minutes", sleep_detail)
        if not m:
            m = re.search(rf"{stage} for (\d+) minutes", sleep_detail)
            if m:
                out[key] = float(int(m.group(1)))
            continue
        out[key] = float(int(m.group(1)) * 60 + int(m.group(2)))
    return out


def sleep_ratios(row: dict[str, Any]) -> dict[str, float]:
    """Deep/REM/core ratios from hours + stage minutes."""
    out: dict[str, float] = {}
    hours = row.get("iphone_sleep_hours")
    if hours is None:
        return out
    total_min = float(hours) * 60.0
    if total_min <= 0:
        return out
    for stage_key, ratio_key in (
        ("iphone_sleep_deep_min", "iphone_sleep_deep_ratio"),
        ("iphone_sleep_rem_min", "iphone_sleep_rem_ratio"),
        ("iphone_sleep_core_min", "iphone_sleep_core_ratio"),
    ):
        val = row.get(stage_key)
        if val is not None:
            out[ratio_key] = float(val) / total_min
    return out
