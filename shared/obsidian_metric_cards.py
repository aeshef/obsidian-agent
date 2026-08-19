"""Obsidian metric cards — same visual language as the cockpit signals strip.

Static HTML (no Dataview). Reading view renders flex cards with accent tops,
uppercase labels, and tabular-nums values.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class MetricCard:
    label: str
    value: str
    accent: str = "var(--text-accent)"
    hint: str = ""


def _card_html(card: MetricCard) -> str:
    label = html.escape((card.label or "").strip())
    value = html.escape((card.value or "").strip())
    hint = html.escape((card.hint or "").strip())
    accent = html.escape((card.accent or "var(--text-accent)").strip())
    hint_block = ""
    if hint:
        hint_block = (
            f'<div style="font-size:0.78em;color:var(--text-muted);margin-top:6px;'
            f'line-height:1.35">{hint}</div>'
        )
    return (
        f'<div style="flex:1 1 120px;min-width:110px;padding:12px 14px;border-radius:12px;'
        f"background:color-mix(in srgb, var(--background-secondary) 90%, transparent);"
        f"border:1px solid var(--background-modifier-border);border-top:3px solid {accent}\">"
        f'<div style="font-size:0.72em;text-transform:uppercase;letter-spacing:.05em;'
        f'color:var(--text-muted);margin-bottom:6px;font-weight:600">{label}</div>'
        f'<div style="font-size:1.45em;font-weight:700;font-variant-numeric:tabular-nums;'
        f'line-height:1.15">{value}</div>'
        f"{hint_block}</div>"
    )


def metric_cards_html(cards: Sequence[MetricCard]) -> str:
    """One flex row of metric cards (HTML fragment)."""
    items = [c for c in cards if (c.label or "").strip() or (c.value or "").strip()]
    if not items:
        return ""
    inner = "".join(_card_html(c) for c in items)
    return (
        f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin:0 0 12px">{inner}</div>'
    )


def metric_cards_lines(cards: Sequence[MetricCard]) -> list[str]:
    """Markdown lines wrapping the HTML row (blank lines for Obsidian HTML parse)."""
    block = metric_cards_html(cards)
    if not block:
        return []
    return ["", block, ""]
