"""System hub — agent cost + audit links only (no life/health insights)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from shared.analytics.hub_hero import render_system_hero
from shared.chart_paths import chart_path, chart_wikilink_png
from shared.vault_paths_config import dashboards_sub, folder, vault_file


def _md_wikilink(key: str, label: str) -> str:
    rel = vault_file(key)
    stem = rel[:-3] if rel.lower().endswith(".md") else rel
    return f"[[{folder('dashboards')}/{dashboards_sub('charts')}/{stem}|{label}]]"


def _png_exists(vault: Path, key: str) -> bool:
    try:
        return chart_path(vault, key).is_file()
    except Exception:
        return False


def _safe_msg(msg: Callable[[str], str], key: str) -> str:
    try:
        text = msg(key)
    except Exception:
        return ""
    if not text or text == key:
        return ""
    return str(text).strip()


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
    ]

    tip = _safe_msg(msg, "system_hub_tip")
    if tip:
        lines.extend([tip.replace("{updated}", ts), "", "---", ""])

    hero = render_system_hero(vault, msg).rstrip()
    if hero:
        lines.extend([hero, "", "---", ""])

    lines.extend([f"## {msg('system_section_agent')}", ""])
    agent_hint = _safe_msg(msg, "system_hint_agent")
    if agent_hint:
        lines.extend([agent_hint, ""])

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
            detail = _safe_msg(msg, "system_link_agent_cost_detail") or "Agent cost detail"
            tip = _safe_msg(msg, "system_agent_cost_detail_tip")
            link = _md_wikilink("agent_cost_dashboard_md", detail)
            if tip:
                lines.extend([tip.replace("{link}", link), ""])
            else:
                lines.extend([f"> [!note]- {detail}", f"> {link}", ""])
    except Exception:
        pass

    lines.append("---")
    lines.append("")

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

    footer = _safe_msg(msg, "system_hub_footer")
    if footer:
        lines.extend([footer, ""])

    return "\n".join(lines).rstrip() + "\n"
