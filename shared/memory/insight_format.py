"""Insight kind normalization, synth parsing, and display formatting."""
from __future__ import annotations

from typing import Any

from shared.domain_messages import dmsg

KIND_DURABLE = "durable"
KIND_PERIODIC = "periodic"


def normalize_kind(raw: str | None) -> str:
    kind = (raw or "").strip().lower()
    if kind == KIND_PERIODIC:
        return KIND_PERIODIC
    return KIND_DURABLE


def parse_synth_patterns(result: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Parse LLM synth JSON into (text, kind) pairs."""
    if not isinstance(result, dict):
        return []
    raw = result.get("patterns")
    if not isinstance(raw, list):
        return []
    out: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("pattern") or "").strip()
            kind = normalize_kind(item.get("kind"))
        else:
            text = str(item).strip()
            kind = KIND_DURABLE
        if text:
            out.append((text, kind))
    return out


def format_date_short(iso_ts: str | None) -> str:
    return (iso_ts or "")[:10] or "?"


def format_confirmed_prompt_line(*, date: str, text: str) -> str:
    return dmsg("memory_insights", "prompt_line", date=date, text=text)


def format_confirmed_ui_line(*, domain: str, date: str, kind: str, text: str) -> str:
    return dmsg(
        "memory_insights",
        "confirmed_ui_line",
        domain=domain,
        date=date,
        kind=kind,
        text=text,
    )


def format_pending_ui_line(
    *,
    domain: str,
    date: str,
    kind: str,
    pid: int,
    text: str,
    count: int,
) -> str:
    return dmsg(
        "memory_insights",
        "pending_ui_line",
        domain=domain,
        date=date,
        kind=kind,
        id=pid,
        text=text,
        count=count,
    )


def group_confirmed_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    durable: list[dict] = []
    periodic: list[dict] = []
    for row in records:
        if normalize_kind(row.get("kind")) == KIND_PERIODIC:
            periodic.append(row)
        else:
            durable.append(row)
    return durable, periodic
