"""Assemble finance dashboard markdown from pre-built section lists."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from bot.dashboard_templates import dtpl
from bot.services.dashboard.format import fmt_num
from shared.finance.currency import base_currency


HERO_META_PLACEHOLDER = "__FINANCE_HERO_META__"


def fill_summary_hero(
    part_summary: list[str],
    *,
    total_rub: float,
    total_usd: float,
    cushion_runway_str: str = "",
) -> None:
    """Replace hero placeholder in ``part_summary`` with metric cards (in place)."""
    if HERO_META_PLACEHOLDER not in part_summary:
        return

    from shared.obsidian_metric_cards import MetricCard, metric_cards_lines

    hero_cards = [
        MetricCard(
            label=dtpl("sections", "summary", "card_total_label") or "Total",
            value=f"{fmt_num(total_rub, decimals=0)} {base_currency()}",
            accent="#1e88e5",
            hint=dtpl("sections", "summary", "card_total_hint") or "cash + broker",
        ),
    ]
    if total_usd != 0:
        hero_cards.append(
            MetricCard(
                label="USD",
                value=f"${fmt_num(total_usd, decimals=0)}",
                accent="#43a047",
            )
        )
    if cushion_runway_str:
        hero_cards.append(
            MetricCard(
                label=dtpl("sections", "summary", "card_cushion_label") or "Cushion",
                value=dtpl("sections", "summary", "card_cushion_value", months=cushion_runway_str)
                or f"{cushion_runway_str} mo",
                accent="#7e57c2",
                hint=dtpl("sections", "summary", "card_cushion_hint") or "cash / essentials",
            )
        )
    idx = part_summary.index(HERO_META_PLACEHOLDER)
    part_summary[idx : idx + 1] = metric_cards_lines(hero_cards)


def assemble_dashboard_markdown(
    *,
    part_summary: Sequence[str],
    part_structure: Sequence[str],
    part_planned: Sequence[str],
    part_exp_pies: Sequence[str],
    part_badge: Sequence[str],
    part_oneoff_list: Sequence[str],
    part_moves: Sequence[str],
    part_exp_by_account: Sequence[str],
    part_balances: Sequence[str],
    part_top_exp: Sequence[str],
) -> str:
    """Join pre-built section line lists into the final dashboard markdown body."""
    sections = list(part_summary) + list(part_planned)

    nav = dtpl("nav_callout")
    nav_block = f"\n\n{nav}\n\n---" if nav.strip() else ""
    return dtpl("title") + nav_block + "\n\n" + "\n".join(sections)


def write_dashboard_md(path: Path, body: str) -> None:
    """Create parent dirs if needed and write dashboard markdown to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
