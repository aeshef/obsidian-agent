"""Badge nutrition dashboard section."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from bot.config_loader import get_badge_config, is_badge_enabled
from bot.dashboard_templates import dtpl
from bot.services.badge_tracker import BadgeTracker
from bot.services.dashboard.charts import plot_stacked_bar_categories_png
from bot.services.dashboard.format import fmt_num


def build_badge_section(
    conn: sqlite3.Connection,
    user_id: int,
    charts_dir: Path,
    now: datetime,
    *,
    vault_root: Optional[Path] = None,
    chart_wikilink: Optional[Callable[[Path], str]] = None,
) -> list[str]:
    """Badge nutrition section for current month."""
    badge_png = charts_dir / dtpl("badge", "chart_file")
    if not is_badge_enabled():
        if badge_png.exists():
            badge_png.unlink()
        return []
    tracker = BadgeTracker(get_badge_config())
    cfg = get_badge_config()
    dash_cfg = cfg.get("dashboard") or {}
    title = dash_cfg.get("section_title") or dtpl("badge", "default_title", default="Badge")
    m = tracker.month_stats_sync(conn, user_id, now.year, now.month)
    if m is None:
        if badge_png.exists():
            badge_png.unlink()
        return [
            f"### {title}",
            "",
            dtpl("badge", "no_account"),
            "",
        ]
    lines = [
        f"### {title} ({now.strftime('%B %Y')})",
        "",
        dtpl("badge", "working_days", days=m.working_days),
        dtpl(
            "badge",
            "spent",
            spent=fmt_num(float(m.total_spent), decimals=0),
            entitlement=fmt_num(float(m.total_entitlement), decimals=0),
            pct=m.utilization_pct,
        ),
        dtpl("badge", "burned", amount=fmt_num(float(m.total_burned), decimals=0)),
    ]
    if dash_cfg.get("show_ndfl_estimate", True):
        lines.append(dtpl("badge", "ndfl", amount=fmt_num(float(m.total_ndfl), decimals=0)))
    lines.append(dtpl("badge", "zero_days", days=m.zero_spend_days))
    if float(m.total_over_limit) > 0:
        lines.append(dtpl("badge", "over_limit", amount=fmt_num(float(m.total_over_limit), decimals=0)))
    lines.append("")

    # Skip empty utilization chart (all burned / zero spend) — looks broken in UI
    wdays = [d for d in m.days if d.is_working_day]
    if wdays and float(m.total_spent) > 0:
        x_labels = [d.date.strftime("%d.%m") for d in wdays]
        spent_vals = [float(d.spent) for d in wdays]
        burned_vals = [float(d.burned) for d in wdays]
        ok = plot_stacked_bar_categories_png(
            x_labels,
            {dtpl("badge", "chart_spent"): spent_vals, dtpl("badge", "chart_burned"): burned_vals},
            title=dtpl("badge", "chart_title"),
            y_label="RUB",
            out_path=badge_png,
            show_total_labels=True,
            totals_for_labels=[float(d.limit) for d in wdays],
        )
        if ok:
            if chart_wikilink:
                lines.append(chart_wikilink(badge_png))
            elif vault_root is not None:
                rel = badge_png.resolve().relative_to(vault_root.resolve())
                lines.append(f"![[{rel.as_posix()}]]")
        elif badge_png.exists():
            badge_png.unlink()
        lines.append("")
    else:
        if float(m.total_spent) <= 0 and float(m.total_burned) > 0:
            lines.append(dtpl("badge", "idle_month"))
            lines.append("")
        if badge_png.exists():
            badge_png.unlink()

    return lines
