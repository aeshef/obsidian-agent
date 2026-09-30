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
    label=html.escape((card.label or "").strip())
    value=html.escape((card.value or "").strip())
    hint=html.escape((card.hint or "").strip())
    return (f'<div class="au-metric"><div class="au-label">{label}</div>'
            f'<div class="au-value">{value}</div>'
            +(f'<div class="au-muted">{hint}</div>' if hint else '')+'</div>')


def metric_cards_html(cards: Sequence[MetricCard]) -> str:
    items=[c for c in cards if (c.label or "").strip() or (c.value or "").strip()]
    if not items:return ""
    return '<div class="au-grid">'+''.join(_card_html(c) for c in items)+'</div>'


def metric_cards_lines(cards: Sequence[MetricCard]) -> list[str]:
    """Markdown lines wrapping the HTML row (blank lines for Obsidian HTML parse)."""
    block = metric_cards_html(cards)
    if not block:
        return []
    return ["", block, ""]
