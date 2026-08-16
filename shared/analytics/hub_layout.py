"""Analytics hub layout — life metrics only (agent → System hub)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from shared.chart_paths import chart_path, chart_wikilink_png
from shared.vault_paths_config import dashboards_sub, folder, vault_file


def _md_embed(key: str) -> str:
    rel = vault_file(key)
    stem = rel[:-3] if rel.lower().endswith(".md") else rel
    return f"![[{dashboards_sub('charts')}/{stem}]]"


def _png_exists(vault: Path, key: str) -> bool:
    return chart_path(vault, key).is_file()


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

    sections: list[tuple[str, list[tuple[str | None, str | None, str | None]]]] = [
        (
            "analytics_section_body",
            [("analytics_sub_weight", "png", "chart_analytics_weight_trend_png")],
        ),
        (
            "analytics_section_sleep",
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
            [
                ("analytics_sub_life_os_scores", "png", "chart_analytics_life_os_scores_png"),
                ("analytics_sub_life_os_regimes", "png", "chart_analytics_life_os_regimes_png"),
            ],
        ),
        (
            "analytics_section_correlations",
            [
                ("analytics_sub_panel_corr", "png", "chart_analytics_panel_corr_png"),
                ("analytics_sub_tasks_sleep", "png", "chart_analytics_tasks_sleep_png"),
            ],
        ),
    ]

    for heading_key, blocks in sections:
        rendered_blocks: list[str] = []
        for subtitle_key, kind, asset_key in blocks:
            if kind == "png" and asset_key and _png_exists(vault, asset_key):
                if subtitle_key:
                    rendered_blocks.append(f"### {msg(subtitle_key)}")
                    rendered_blocks.append("")
                rendered_blocks.append(chart_wikilink_png(asset_key))
                rendered_blocks.append("")
        if not rendered_blocks:
            continue
        lines.append(f"## {msg(heading_key)}")
        lines.append("")
        lines.extend(rendered_blocks)
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
