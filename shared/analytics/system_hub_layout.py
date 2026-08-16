"""System hub — agent cost + audit links only (no life/health insights)."""
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
    try:
        return chart_path(vault, key).is_file()
    except Exception:
        return False


def render_system_hub(
    vault: Path,
    *,
    ts: str,
    msg: Callable[[str], str],
) -> str:
    dash = folder("dashboards")
    lines: list[str] = [
        f"# {msg('system_hub_title')}",
        "",
        msg("system_nav_callout").strip(),
        "",
        "---",
        "",
        f"## {msg('system_section_agent')}",
        "",
    ]
    if _png_exists(vault, "chart_agent_cost_daily_png"):
        lines.extend(
            [
                f"### {msg('system_sub_agent_cost')}",
                "",
                chart_wikilink_png("chart_agent_cost_daily_png"),
                "",
            ]
        )
    if _png_exists(vault, "chart_agent_tokens_daily_png"):
        lines.extend(
            [
                f"### {msg('system_sub_agent_tokens')}",
                "",
                chart_wikilink_png("chart_agent_tokens_daily_png"),
                "",
            ]
        )
    if _png_exists(vault, "chart_agent_tools_png"):
        lines.extend(
            [
                f"### {msg('system_sub_agent_tools')}",
                "",
                chart_wikilink_png("chart_agent_tools_png"),
                "",
            ]
        )
    try:
        if chart_path(vault, "agent_cost_dashboard_md").is_file():
            lines.extend([_md_embed("agent_cost_dashboard_md"), ""])
    except Exception:
        pass

    audit_lines: list[str] = []
    for key, label_key in (
        ("system_audit_report_md", "system_link_system_audit"),
        ("vault_audit_report_md", "system_link_vault_audit"),
    ):
        try:
            name = vault_file(key)
            p = vault / dash / name
            if p.is_file():
                audit_lines.append(f"- [[{dash}/{name}|{msg(label_key)}]]")
        except Exception:
            continue
    if audit_lines:
        lines.extend([f"## {msg('system_section_audits')}", ""] + audit_lines + [""])

    return "\n".join(lines).rstrip() + "\n"
