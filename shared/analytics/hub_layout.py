"""Analytics hub layout — sections, no duplicate chart embeds."""
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
    """Build hub markdown: one chart per subsection, text-only overview embed."""
    dash = folder("dashboards")
    health = vault_file("health_dashboard_md")
    nav = msg("analytics_nav_callout").strip()
    lines: list[str] = [
        f"# {msg('analytics_hub_title')}",
        "",
        nav,
        "",
        msg("analytics_hub_tip").replace("{updated}", ts),
        "",
        "---",
        "",
    ]

    sections: list[tuple[str, list[tuple[str | None, str | None, str | None]]]] = [
        (
            "analytics_section_overview",
            [(None, "md", "chart_analytics_insights_md")],
        ),
        (
            "analytics_section_body",
            [("analytics_sub_weight", "png", "chart_analytics_weight_trend_png")],
        ),
        (
            "analytics_section_sleep",
            [
                ("analytics_sub_sleep_hours", "png", "chart_analytics_sleep_trend_png"),
                ("analytics_sub_sleep_stages", "png", "chart_analytics_sleep_stages_png"),
                ("analytics_sub_sleep_weight", "png", "chart_analytics_sleep_weight_png"),
                ("analytics_sub_sleep_heatmap", "png", "chart_analytics_sleep_heatmap_png"),
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
            if kind == "md":
                rendered_blocks.append(_md_embed(asset_key))
                rendered_blocks.append("")
                continue
            if kind == "png" and asset_key and _png_exists(vault, asset_key):
                block_lines: list[str] = []
                if subtitle_key:
                    block_lines.append(f"### {msg(subtitle_key)}")
                    block_lines.append("")
                block_lines.append(chart_wikilink_png(asset_key))
                block_lines.append("")
                rendered_blocks.extend(block_lines)

        if not rendered_blocks:
            continue

        lines.append(f"## {msg(heading_key)}")
        lines.append("")
        lines.extend(rendered_blocks)
        if rendered_blocks and rendered_blocks[-1].strip():
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"## {msg('analytics_section_cross')}")
    lines.append("")
    lines.append(msg("analytics_cross_health_link").replace("{health_dashboard}", f"{dash}/{health}"))
    lines.append("")
    lines.append("---")
    lines.append("")
    data_files = msg("analytics_data_files")
    if data_files.strip():
        lines.append(f"> [!note]- {msg('analytics_section_data')}")
        for data_line in data_files.strip().splitlines():
            lines.append(f"> {data_line}" if data_line.strip() else ">")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
