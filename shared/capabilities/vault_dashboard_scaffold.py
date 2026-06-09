"""Scaffold Obsidian dashboard markdown from locale YAML + vault_paths + kanban_schema."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from shared.capabilities.features import feature_enabled
from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    get_capabilities,
)
from shared.constants import goals_year
from shared.locale import agent_locale
from shared.paths import VaultPaths
from shared.vault_paths_config import dashboards_sub, finance_sub, folder, vault_file
from shared.yaml_config import load_runtime_config, load_yaml

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO / "vault-templates" / "dashboards"
_MODULE_ALIASES = {
    "finance": MODULE_FINANCE,
    "planning": MODULE_PLANNING,
    "knowledge": MODULE_KNOWLEDGE,
}


def _locale() -> str:
    loc = (os.environ.get("AGENT_LOCALE") or agent_locale() or "en").strip().lower()
    return "ru" if loc.startswith("ru") else "en"


@lru_cache(maxsize=2)
def _dashboards_catalog(locale: str | None = None) -> dict:
    loc = locale or _locale()
    cfg = load_runtime_config(str(_REPO / "config"), f"vault_dashboards.{loc}")
    if not cfg:
        path = _REPO / "config" / f"vault_dashboards.{loc}.yaml.example"
        cfg = load_yaml(path, default={}) or {}
    return cfg if isinstance(cfg, dict) else {}


def _kanban_schema() -> dict:
    path = _REPO / "planning_bot" / "config" / "kanban_schema.yaml"
    if not path.is_file():
        path = _REPO / "planning_bot" / "config" / "kanban_schema.yaml.example"
    return load_yaml(path, default={}) or {}


def _json_js(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False)


def _substitute(text: str, ctx: dict[str, str]) -> str:
    out = text
    for key, val in ctx.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def _render_template(name: str, ctx: dict[str, str]) -> str:
    path = _TEMPLATES / name
    if not path.is_file():
        return f"<!-- missing template: {name} -->\n"
    return _substitute(path.read_text(encoding="utf-8"), ctx)


def _module_active(modules: list[str], prof: CapabilityProfile) -> bool:
    if not modules:
        return True
    return any(prof.module(_MODULE_ALIASES.get(m, m)) for m in modules)


def _block_active(spec: dict, prof: CapabilityProfile) -> bool:
    if not _module_active(list(spec.get("modules") or []), prof):
        return False
    feat = (spec.get("feature") or "").strip()
    if feat and not feature_enabled(feat, prof):
        return False
    return True


def build_scaffold_context(
    prof: Optional[CapabilityProfile] = None,
    vault_root: Optional[Path] = None,
    *,
    locale: str | None = None,
) -> dict[str, str]:
    prof = prof or get_capabilities()
    loc = locale or _locale()
    catalog = _dashboards_catalog(loc)
    strings = catalog.get("strings") if isinstance(catalog.get("strings"), dict) else {}
    schema = _kanban_schema()
    year = goals_year()
    vp = VaultPaths(vault_root) if vault_root else VaultPaths()

    tags = schema.get("tag_prefixes") or {}
    tag_goal = str(tags.get("goal") or "goal")
    tag_priority = str(tags.get("priority") or "priority")
    tag_focus = str(tags.get("focus") or "focus")
    tag_deadline = str(tags.get("deadline") or "deadline")

    categories = list(schema.get("categories") or [])
    category_order = schema.get("category_order") or {}
    sorted_cats = sorted(categories, key=lambda c: int(category_order.get(c, 99)))
    priorities = list(schema.get("priorities") or [])
    priority_order = schema.get("priority_order") or {}
    category_emojis = schema.get("category_emojis") or {}
    priority_emojis = schema.get("priority_emojis") or {}

    columns = list(schema.get("columns") or [])
    done_column = columns[-1] if columns else "Done"

    goals_page = f"{folder('goals')}/{vault_file('goals_template', year=year)}"
    kanban_page = f"{folder('tasks')}/{vault_file('kanban_board')}"
    dash_folder = folder("dashboards")
    charts_sub = dashboards_sub("charts")
    data_sub = dashboards_sub("data")
    mapping_path = f"{dash_folder}/{vault_file('goals_mapping_json')}"
    calendar_dash = vault_file("calendar_dashboard_md")
    calendar_json = vault_file("calendar_json")
    nutrition_dash = f"{dash_folder}/{vault_file('nutrition_dashboard_md')}"
    finance_dash = f"{dash_folder}/{finance_sub('dashboard_md')}"

    quarter_names = strings.get("quarter_names") if isinstance(strings.get("quarter_names"), dict) else {}
    q_names_js = {
        k: str(v).format(year=year) for k, v in quarter_names.items()
    }

    ctx: dict[str, str] = {
        "year": str(year),
        "goals_page": goals_page,
        "kanban_page": kanban_page,
        "mapping_path": mapping_path,
        "charts_subdir": charts_sub,
        "data_subdir": data_sub,
        "calendar_dashboard": f"{dash_folder}/{calendar_dash}",
        "calendar_json": calendar_json,
        "nutrition_dashboard": nutrition_dash,
        "finance_dashboard": finance_dash,
        "done_column": done_column,
        "tag_goal": tag_goal,
        "tag_priority": tag_priority,
        "tag_focus": tag_focus,
        "tag_deadline": tag_deadline,
        "categories_json": _json_js(categories),
        "category_order_json": _json_js(sorted_cats),
        "priorities_json": _json_js(priorities),
        "priority_order_json": _json_js(priority_order),
        "category_emojis_json": _json_js(category_emojis),
        "priority_emojis_json": _json_js(priority_emojis),
        "quarter_names_json": _json_js(q_names_js),
        "priority_regex": str(schema.get("tag_priority_regex") or "").replace("\\", "\\\\"),
        "label_no_category": str(strings.get("label_no_category") or "uncategorized"),
        "label_no_priority": str(strings.get("label_no_priority") or "no priority"),
        "goals_not_found": str(strings.get("goals_not_found") or ""),
        "no_focus_tasks": str(strings.get("no_focus_tasks") or ""),
        "add_focus_hint": str(strings.get("add_focus_hint") or ""),
        "open_goals": str(strings.get("open_goals") or ""),
        "quarter_focus_heading": str(strings.get("quarter_focus_heading") or ""),
        "quarter_progress_heading": str(strings.get("quarter_progress_heading") or ""),
        "no_quarter_focus": str(strings.get("no_quarter_focus") or ""),
        "kanban_not_found": str(strings.get("kanban_not_found") or ""),
        "mapping_not_found": str(strings.get("mapping_not_found") or ""),
        "mapping_error": str(strings.get("mapping_error") or ""),
        "no_mapped_tasks": str(strings.get("no_mapped_tasks") or ""),
        "goals_mapping_heading": str(strings.get("goals_mapping_heading") or ""),
        "category_progress_heading": str(strings.get("category_progress_heading") or ""),
        "no_categorized_tasks": str(strings.get("no_categorized_tasks") or ""),
        "table_quarter": str(strings.get("table_quarter") or "Quarter"),
        "table_goals": str(strings.get("table_goals") or "Goals"),
        "table_progress": str(strings.get("table_progress") or "Progress"),
        "table_goal": str(strings.get("table_goal") or "Goal"),
        "table_tasks": str(strings.get("table_tasks") or "Tasks"),
        "table_category": str(strings.get("table_category") or "Category"),
        "finance_embed_title": str(strings.get("finance_embed_title") or ""),
        "finance_embed_body": str(strings.get("finance_embed_body") or ""),
        "footer": str(strings.get("footer") or ""),
        "preamble_tip": str(strings.get("preamble_tip") or ""),
        "chart_deadline_md": vault_file("chart_deadline_horizon_md"),
    }

    for key, val in strings.items():
        if key in ("quarter_names",):
            continue
        if isinstance(val, str) and key not in ctx:
            ctx[key] = _substitute(val, ctx)

    return ctx


def _render_block(block_id: str, spec: dict, ctx: dict[str, str]) -> str:
    tpl = str(spec.get("template") or "")
    if not tpl:
        return ""
    extra = dict(ctx)
    heading_key = spec.get("heading_key")
    if heading_key:
        extra["heading"] = ctx.get(str(heading_key), "")
    title_key = spec.get("title_key")
    body_key = spec.get("body_key")
    if title_key:
        extra["chart_title"] = ctx.get(str(title_key), "")
    if body_key:
        extra["chart_body"] = ctx.get(str(body_key), "")
    chart_md_key = spec.get("chart_md_key")
    if chart_md_key:
        md_name = vault_file(str(chart_md_key))
        stem = re.sub(r"\.md$", "", md_name, flags=re.I)
        extra["chart_embed"] = f"![[{ctx['charts_subdir']}/{stem}]]"
    return _render_template(tpl, extra)


def scaffold_vault_dashboards(
    prof: Optional[CapabilityProfile] = None,
    vault_root: Optional[Path] = None,
    *,
    locale: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> list[str]:
    """Write dashboard markdown files; return list of created/updated paths."""
    prof = prof or get_capabilities()
    root = vault_root or VaultPaths().root
    catalog = _dashboards_catalog(locale or _locale())
    dashboards = catalog.get("dashboards") if isinstance(catalog.get("dashboards"), dict) else {}
    blocks = catalog.get("blocks") if isinstance(catalog.get("blocks"), dict) else {}
    ctx = build_scaffold_context(prof, root, locale=locale)
    written: list[str] = []

    for dash_id, dash_spec in dashboards.items():
        if not isinstance(dash_spec, dict):
            continue
        file_key = str(dash_spec.get("file_key") or "")
        if not file_key:
            continue
        out_name = vault_file(file_key)
        out_path = root / folder("dashboards") / out_name
        parts: list[str] = []
        for block_id in dash_spec.get("blocks") or []:
            bid = str(block_id)
            spec = blocks.get(bid)
            if not isinstance(spec, dict):
                continue
            if not _block_active(spec, prof):
                continue
            chunk = _render_block(bid, spec, ctx).strip()
            if chunk:
                parts.append(chunk)
        if not parts:
            continue
        body = "\n\n".join(parts) + "\n"
        if out_path.is_file() and not force:
            continue
        if dry_run:
            written.append(f"(dry-run) {out_path}")
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
        written.append(str(out_path))
    return written
