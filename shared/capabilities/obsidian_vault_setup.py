"""Install Obsidian vault assets from repo templates (plugins config, Templater, clones)."""
from __future__ import annotations

import json
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from shared.capabilities.profile import (
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    get_capabilities,
)
from shared.locale import agent_locale
from shared.paths import VaultPaths
from shared.vault_paths_config import folder, vault_file, vault_rel_path
from shared.yaml_config import load_runtime_config, load_yaml

_REPO = Path(__file__).resolve().parents[2]
_OBSIDIAN_TEMPLATES = _REPO / "vault-templates" / "obsidian"
_TEMPLATER_TEMPLATES = _REPO / "vault-templates" / "templater"


def _locale() -> str:
    loc = (agent_locale() or "en").strip().lower()
    return "ru" if loc.startswith("ru") else "en"


@lru_cache(maxsize=2)
def _obsidian_setup_catalog(locale: str | None = None) -> dict:
    loc = locale or _locale()
    cfg = load_runtime_config(str(_REPO / "config"), f"obsidian_setup.{loc}")
    if not cfg:
        path = _REPO / "config" / f"obsidian_setup.{loc}.yaml.example"
        cfg = load_yaml(path, default={}) or {}
    return cfg if isinstance(cfg, dict) else {}


def _kanban_schema() -> dict:
    path = _REPO / "planning_bot" / "config" / "kanban_schema.yaml"
    if not path.is_file():
        path = _REPO / "planning_bot" / "config" / "kanban_schema.yaml.example"
    return load_yaml(path, default={}) or {}


def _substitute(text: str, ctx: dict[str, str]) -> str:
    out = text
    for key, val in ctx.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def _json_js(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False)


def _category_labels(categories: list[str], emojis: dict) -> list[str]:
    labels: list[str] = []
    for cat in categories:
        em = str(emojis.get(cat) or "").strip()
        name = cat[:1].upper() + cat[1:] if cat else cat
        labels.append(f"{em} {name}".strip() if em else name)
    return labels


def _priority_labels(priorities: list[str], emojis: dict) -> list[str]:
    labels: list[str] = []
    for p in priorities:
        em = str(emojis.get(p) or "").strip()
        name = p[:1].upper() + p[1:] if p else p
        labels.append(f"{em} {name}".strip() if em else name)
    return labels


def build_add_task_context(
    vault_root: Optional[Path] = None,
    *,
    locale: str | None = None,
) -> dict[str, str]:
    loc = locale or _locale()
    catalog = _obsidian_setup_catalog(loc)
    strings = catalog.get("strings") if isinstance(catalog.get("strings"), dict) else {}
    schema = _kanban_schema()

    tags = schema.get("tag_prefixes") or {}
    categories = list(schema.get("categories") or [])
    priorities = list(schema.get("priorities") or [])
    category_emojis = schema.get("category_emojis") or {}
    priority_emojis = schema.get("priority_emojis") or {}
    columns = list(schema.get("columns") or [])
    backlog = columns[0] if columns else "Backlog"

    kanban_page = f"{folder('tasks')}/{vault_file('kanban_board')}"
    kanban_board_basename = Path(vault_file("kanban_board")).stem

    task_meta = str(schema.get("task_meta_template") or "\t#goal/{category} #priority/{priority}")
    task_created = str(schema.get("task_created_template") or "\tCreated: {created_date}")

    ctx: dict[str, str] = {
        "kanban_page": kanban_page,
        "kanban_board_basename": kanban_board_basename,
        "backlog_column": f"## {backlog}",
        "tag_deadline": str(tags.get("deadline") or "deadline"),
        "categories_json": _json_js(categories),
        "category_labels_json": _json_js(_category_labels(categories, category_emojis)),
        "priorities_json": _json_js(priorities),
        "priority_labels_json": _json_js(_priority_labels(priorities, priority_emojis)),
        "task_meta_js": json.dumps(task_meta, ensure_ascii=False),
        "task_created_js": json.dumps(task_created, ensure_ascii=False),
    }
    for key, val in strings.items():
        if isinstance(val, str):
            ctx[key] = val.replace("\n", " ").strip() if key.startswith("add_task_notice") else val.strip()
    return ctx


def _copy_tree(src: Path, dst: Path, *, force: bool) -> list[str]:
    if not src.is_dir():
        return []
    written: list[str] = []
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.rglob("*")):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if target.is_file() and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        written.append(str(target))
    return written


def _write_text(path: Path, body: str, *, force: bool) -> bool:
    if path.is_file() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
    return True


def install_obsidian_assets(
    prof: Optional[CapabilityProfile] = None,
    vault_root: Optional[Path] = None,
    *,
    locale: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Copy Obsidian templates/snippets and render Templater scripts into the vault."""
    prof = prof or get_capabilities()
    root = vault_root or VaultPaths().root
    loc = locale or _locale()
    written: list[str] = []

    # Finance-only: skip Obsidian template trees (no kanban/KB templates needed)
    if not prof.any_module(MODULE_PLANNING, MODULE_KNOWLEDGE):
        return written

    automation = root / folder("automation")
    clones_dst = automation / vault_rel_path("templates_clones")
    v2_dst = automation / vault_rel_path("templates_v2")
    entities_dst = automation / vault_rel_path("templates_entities")

    clones_src = _OBSIDIAN_TEMPLATES / "clones"
    entities_src = _OBSIDIAN_TEMPLATES / "entities" / loc
    if not entities_src.is_dir():
        entities_src = _OBSIDIAN_TEMPLATES / "entities" / "ru"

    if dry_run:
        return [f"(dry-run) obsidian assets → {automation}"]

    # Clones/entities: planning or knowledge
    if clones_src.is_dir() and prof.any_module(MODULE_PLANNING, MODULE_KNOWLEDGE):
        written.extend(_copy_tree(clones_src, clones_dst, force=force))

    if entities_src.is_dir() and prof.module(MODULE_PLANNING):
        written.extend(_copy_tree(entities_src, entities_dst, force=force))

    snippets_src = _OBSIDIAN_TEMPLATES / "snippets"
    snippets_dst = root / ".obsidian" / "snippets"
    if snippets_src.is_dir():
        written.extend(_copy_tree(snippets_src, snippets_dst, force=force))

    plugins_src = _OBSIDIAN_TEMPLATES / "config" / "community-plugins.json"
    plugins_dst = root / ".obsidian" / "community-plugins.json"
    if plugins_src.is_file() and (force or not plugins_dst.is_file()):
        plugins_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugins_src, plugins_dst)
        written.append(str(plugins_dst))

    templater_folder = f"{folder('automation')}/{vault_rel_path('templates_v2')}"
    tpl_path = _OBSIDIAN_TEMPLATES / "config" / "templater-data.json.template"
    if tpl_path.is_file() and prof.module(MODULE_PLANNING):
        body = _substitute(tpl_path.read_text(encoding="utf-8"), {"templater_folder": templater_folder})
        t_dst = root / ".obsidian" / "plugins" / "templater-obsidian" / "data.json"
        if _write_text(t_dst, body, force=force):
            written.append(str(t_dst))

    if prof.module(MODULE_PLANNING):
        add_tpl = _TEMPLATER_TEMPLATES / "add_task.md.template"
        if add_tpl.is_file():
            ctx = build_add_task_context(root, locale=loc)
            body = _substitute(add_tpl.read_text(encoding="utf-8"), ctx)
            out_name = vault_file("templater_add_task_md")
            out_path = v2_dst / out_name
            if _write_text(out_path, body, force=force):
                written.append(str(out_path))

    return written


def required_plugins(locale: str | None = None) -> list[str]:
    catalog = _obsidian_setup_catalog(locale)
    plugins = catalog.get("plugins") if isinstance(catalog.get("plugins"), dict) else {}
    req = plugins.get("required")
    return [str(p) for p in req] if isinstance(req, list) else []
