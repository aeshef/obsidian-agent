"""Badge nutrition dashboard section."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from bot.config_loader import get_badge_config, is_badge_enabled
from bot.dashboard_templates import dtpl
from bot.services.badge_tracker import BadgeTracker
from bot.services.dashboard.format import fmt_num
from shared.finance.currency import base_currency


def build_badge_section(
    conn: sqlite3.Connection,
    user_id: int,
    charts_dir: Path,
    now: datetime,
    *,
    vault_root: Optional[Path] = None,
    chart_specs: Optional[list] = None,
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
    if dash_cfg.get("show_ndfl_estimate", False):
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
        if chart_specs is not None:
            from shared.obsidian_ui.series import series_chart
            chart_specs.append(series_chart('badge',dtpl('badge','chart_title'),[d.date for d in wdays],
                {dtpl('badge','chart_spent'):spent_vals,dtpl('badge','chart_burned'):burned_vals},
                method='sum',chart_type='bar',unit=base_currency(),filter_fields=[]))
    else:
        if float(m.total_spent) <= 0 and float(m.total_burned) > 0:
            lines.append(dtpl("badge", "idle_month"))
            lines.append("")
        if badge_png.exists():
            badge_png.unlink()

    return lines
