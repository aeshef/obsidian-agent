"""Analytics hub layout — life metrics only (agent → System hub)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from shared.analytics.hub_hero import render_analytics_hero
from shared.chart_paths import chart_path, chart_wikilink_png
from shared.vault_paths_config import dashboards_sub, folder, vault_file


def _md_embed(key: str) -> str:
    rel = vault_file(key)
    stem = rel[:-3] if rel.lower().endswith(".md") else rel
    return f"![[{folder('dashboards')}/{dashboards_sub('charts')}/{stem}]]"


def _png_exists(vault: Path, key: str) -> bool:
    return chart_path(vault, key).is_file()


def _safe_msg(msg: Callable[[str], str], key: str) -> str:
    try:
        text = msg(key)
    except Exception:
        return ""
    if not text or text == key:
        return ""
    return str(text).strip()


def render_analytics_hub(
    vault: Path,
    *,
    ts: str,
    msg: Callable[[str], str],
) -> str:
    """Build hub markdown: charts + insights note. No meta tips."""
    lines: list[str] = [
        f"# {msg('analytics_hub_title')}",
        "",
        msg("analytics_nav_callout").strip(),
        "",
        "---",
        "",
    ]

    tip = _safe_msg(msg, "analytics_hub_tip")
    if tip:
        lines.extend([tip.replace("{updated}", ts), "", "---", ""])

    hero = render_analytics_hero(vault, msg).rstrip()
    if hero:
        lines.extend([hero, "", "---", ""])

    # Sleep hypotheses text lives with life analytics, not System
    try:
        if chart_path(vault, "chart_analytics_insights_md").is_file():
            lines.extend(
                [
                    f"## {msg('analytics_section_insights')}",
                    "",
                    _md_embed("chart_analytics_insights_md"),
                    "",
                    "---",
                    "",
                ]
            )
    except Exception:
        pass

    # (heading_key, optional_hint_key, blocks)
    sections: list[tuple[str, str | None, list[tuple[str | None, str, str]]]] = [
        (
            "analytics_section_body",
            "analytics_hint_body",
            [("analytics_sub_weight", "png", "chart_analytics_weight_trend_png")],
        ),
        (
            "analytics_section_sleep",
            "analytics_hint_sleep",
            [
                ("analytics_sub_sleep_hours", "png", "chart_analytics_sleep_trend_png"),
                ("analytics_sub_sleep_debt", "png", "chart_analytics_sleep_debt_png"),
                ("analytics_sub_sleep_stages", "png", "chart_analytics_sleep_stages_png"),
                ("analytics_sub_sleep_weight", "png", "chart_analytics_sleep_weight_png"),
                ("analytics_sub_sleep_heatmap", "png", "chart_analytics_sleep_heatmap_png"),
            ],
        ),
        (
            "analytics_section_life_os",
            "analytics_life_os_legend",
            [
                ("analytics_sub_life_os_scores", "png", "chart_analytics_life_os_scores_png"),
                ("analytics_sub_life_os_regimes", "png", "chart_analytics_life_os_regimes_png"),
            ],
        ),
        (
            "analytics_section_correlations",
            "analytics_hint_correlations",
            [
                ("analytics_sub_panel_corr", "png", "chart_analytics_panel_corr_png"),
                ("analytics_sub_tasks_sleep", "png", "chart_analytics_tasks_sleep_png"),
            ],
        ),
    ]

    for heading_key, hint_key, blocks in sections:
        rendered_blocks: list[str] = []
        for subtitle_key, kind, asset_key in blocks:
            if kind == "png" and asset_key and _png_exists(vault, asset_key):
                if subtitle_key:
                    rendered_blocks.append(f"### {msg(subtitle_key)}")
                    rendered_blocks.append("")
                chart_hint_key = f"{subtitle_key}_hint" if subtitle_key else ""
                chart_hint = _safe_msg(msg, chart_hint_key) if chart_hint_key else ""
                if chart_hint:
                    rendered_blocks.append(chart_hint)
                    rendered_blocks.append("")
                rendered_blocks.append(chart_wikilink_png(asset_key))
                rendered_blocks.append("")
        if not rendered_blocks:
            continue
        lines.append(f"## {msg(heading_key)}")
        lines.append("")
        if hint_key:
            hint = _safe_msg(msg, hint_key)
            if hint:
                lines.append(hint)
                lines.append("")
        lines.extend(rendered_blocks)
        lines.append("---")
        lines.append("")

    cross = _safe_msg(msg, "analytics_cross_health_link")
    if cross:
        health = vault_file("health_dashboard_md")
        cross = cross.replace("{health_dashboard}", f"{folder('dashboards')}/{health}")
        lines.extend([cross, ""])

    return "\n".join(lines).rstrip() + "\n"
