"""Scaffold Obsidian routines/signals statistics markdown from locale YAML + vault_paths."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from planning_bot.app.ui import pmsg
from planning_bot.services.routines_config import section_config_header, section_history_label
from shared.capabilities.profile import MODULE_PLANNING, CapabilityProfile, get_capabilities
from shared.locale import agent_locale
from shared.paths import VaultPaths
from shared.routines_paths import (
    routines_config_wikilink,
    routines_history_wikilink,
    routines_root,
    routines_stats_path,
    signals_dir,
    signals_history_wikilink,
    signals_stats_path,
)
from shared.vault_paths_config import folder, vault_file
from shared.yaml_config import load_runtime_config, load_yaml

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO / "vault-templates" / "routines"
_DV_READ = _TEMPLATES / "dv_read_note.snippet"


def _locale() -> str:
    loc = (os.environ.get("AGENT_LOCALE") or agent_locale() or "en").strip().lower()
    return "ru" if loc.startswith("ru") else "en"


@lru_cache(maxsize=2)
def _routines_catalog(locale: str | None = None) -> dict:
    loc = locale or _locale()
    cfg = load_runtime_config(str(_REPO / "config"), f"vault_routines.{loc}")
    if not cfg:
        path = _REPO / "config" / f"vault_routines.{loc}.yaml.example"
        cfg = load_yaml(path, default={}) or {}
    return cfg if isinstance(cfg, dict) else {}


def _substitute(text: str, ctx: dict[str, str]) -> str:
    out = text
    for key, val in ctx.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def _msg(key: str, catalog: dict, catalog_key: str, default: str = "") -> str:
    val = pmsg(key)
    if val and not val.startswith(("routines_", "signals_")):
        return val
    strings = catalog.get("strings") if isinstance(catalog.get("strings"), dict) else {}
    return str(strings.get(catalog_key) or default)


def _signals_yaml_template_body() -> str:
    path = _TEMPLATES / "signals_config.yaml.template"
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out).strip()


def build_scaffold_context(
    prof: Optional[CapabilityProfile] = None,
    vault_root: Optional[Path] = None,
    *,
    locale: str | None = None,
) -> dict[str, str]:
    prof = prof or get_capabilities()
    loc = locale or _locale()
    catalog = _routines_catalog(loc)
    strings = catalog.get("strings") if isinstance(catalog.get("strings"), dict) else {}
    ctx = {
        "routines_stats_title": _msg("routines_stats_title", catalog, "routines_stats_title", "# 📊 Routine statistics"),
        "routines_stats_subtitle": _msg(
            "routines_stats_subtitle", catalog, "routines_stats_subtitle", ""
        ),
        "routines_stats_footer": _msg("routines_stats_footer", catalog, "routines_stats_footer", ""),
        "signals_stats_title": _msg("signals_stats_title", catalog, "signals_stats_title", "# 📊 Signals statistics"),
        "signals_stats_subtitle": _msg(
            "signals_stats_subtitle", catalog, "signals_stats_subtitle", ""
        ),
        "signals_stats_footer": _msg("signals_stats_footer", catalog, "signals_stats_footer", ""),
        "history_page": routines_history_wikilink(),
        "config_page": routines_config_wikilink(),
        "signals_history_page": signals_history_wikilink(),
        "routines_history_link": routines_history_wikilink(),
        "signals_history_link": signals_history_wikilink(),
        "signals_config_title": _msg(
            "signals_config_title", catalog, "signals_config_title", "📋 Signals configuration"
        ),
        "signals_config_intro": str(strings.get("signals_config_intro") or ""),
        "signals_config_yaml_body": _signals_yaml_template_body(),
        "morning_config_header": section_config_header("morning"),
        "day_config_header": section_config_header("day"),
        "evening_config_header": section_config_header("evening"),
        "morning_history_label": section_history_label("morning"),
        "day_history_label": section_history_label("day"),
        "evening_history_label": section_history_label("evening"),
        "stats_empty_history": str(strings.get("stats_empty_history") or ""),
        "stats_no_dates": str(strings.get("stats_no_dates") or ""),
        "dv_read_note": _DV_READ.read_text(encoding="utf-8") if _DV_READ.is_file() else "",
    }
    return ctx


_SIGNALS_FILE_TEMPLATES = (
    ("signals_config_md", "signals_config.md.template"),
)


def _scaffold_signals_files(
    root: Path,
    ctx: dict[str, str],
    *,
    dry_run: bool = False,
    force: bool = False,
) -> list[str]:
    written: list[str] = []
    base = signals_dir(root)
    for file_key, template_name in _SIGNALS_FILE_TEMPLATES:
        tpl_path = _TEMPLATES / template_name
        if not tpl_path.is_file():
            continue
        out_path = base / vault_file(file_key)
        if out_path.is_file() and not force:
            continue
        body = _substitute(tpl_path.read_text(encoding="utf-8"), ctx).strip() + "\n"
        if dry_run:
            written.append(f"(dry-run) {out_path}")
            continue
        base.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
        written.append(str(out_path))
    return written


def scaffold_vault_routines(
    prof: Optional[CapabilityProfile] = None,
    vault_root: Optional[Path] = None,
    *,
    locale: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> list[str]:
    prof = prof or get_capabilities()
    if not prof.module(MODULE_PLANNING):
        return []
    root = vault_root or VaultPaths().root
    catalog = _routines_catalog(locale or _locale())
    dashboards = catalog.get("dashboards") if isinstance(catalog.get("dashboards"), dict) else {}
    ctx = build_scaffold_context(prof, root, locale=locale)
    written: list[str] = []
    written.extend(_scaffold_signals_files(root, ctx, dry_run=dry_run, force=force))

    for dash_id, spec in dashboards.items():
        if not isinstance(spec, dict):
            continue
        file_key = str(spec.get("file_key") or "")
        template = str(spec.get("template") or "")
        if not file_key or not template:
            continue
        tpl_path = _TEMPLATES / template
        if not tpl_path.is_file():
            continue
        body = _substitute(tpl_path.read_text(encoding="utf-8"), ctx).strip() + "\n"
        out_path = routines_root(root) / vault_file(file_key)
        if out_path.is_file() and not force:
            continue
        if dry_run:
            written.append(f"(dry-run) {out_path}")
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
        written.append(str(out_path))

    return written


def routines_stats_target(vault_root: Optional[Path] = None) -> Path:
    return routines_stats_path(vault_root)


def signals_stats_target(vault_root: Optional[Path] = None) -> Path:
    return signals_stats_path(vault_root)
