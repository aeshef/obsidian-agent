"""Create vault folders for enabled modules (idempotent)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    get_capabilities,
)
from shared.paths import VaultPaths
from shared.vault_layout import knowledge_subdir
from shared.vault_paths_config import dashboards_sub, finance_sub, folder, routines_sub, vault_file, vault_rel_path


def _mkdir(p: Path) -> list[str]:
    if p.exists():
        return []
    p.mkdir(parents=True, exist_ok=True)
    return [str(p)]


def planned_vault_dirs(
    profile: Optional[CapabilityProfile] = None,
    vault_root: Optional[Path] = None,
) -> list[Path]:
    """Directories to ensure for this capability profile."""
    prof = profile or get_capabilities()
    root = vault_root or VaultPaths().root
    paths: list[Path] = []

    needs_dash = prof.any_module(MODULE_FINANCE, MODULE_PLANNING, MODULE_KNOWLEDGE)
    data_dir: Optional[Path] = None
    if needs_dash:
        dash = root / folder("dashboards")
        data_dir = dash / dashboards_sub("data")
        paths.extend(
            [
                dash,
                dash / dashboards_sub("logs"),
                dash / dashboards_sub("charts"),
                data_dir,
            ]
        )
    if prof.module(MODULE_PLANNING) and data_dir is not None:
        routines_root = root / folder("routines")
        paths.extend(
            [
                root / folder("tasks"),
                root / folder("goals"),
                routines_root,
                routines_root / vault_file("routines_calendar_subdir").rstrip("/"),
                routines_root / vault_file("signals_subdir").rstrip("/"),
                routines_root / routines_sub("data"),
                routines_root / routines_sub("charts"),
                routines_root / routines_sub("charts") / routines_sub("charts_routines"),
                routines_root / routines_sub("charts") / routines_sub("charts_signals"),
                root / folder("handwritten"),
            ]
        )
        # Mac/iPhone action sinks only when those connectors are on
        if prof.connector("mac_context"):
            paths.append(data_dir / vault_rel_path("actions_mac"))
        if prof.connector("apple_health") or prof.connector("apple_calendar") or prof.connector("gmail_health_pipeline"):
            paths.append(data_dir / vault_rel_path("actions_iphone"))
    if prof.module(MODULE_FINANCE) and needs_dash:
        paths.append((root / folder("dashboards") / dashboards_sub("charts")) / finance_sub("graphs_finance"))
    if prof.module(MODULE_KNOWLEDGE):
        kb = root / knowledge_subdir()
        auto = root / folder("automation")
        paths.extend(
            [
                kb,
                kb / vault_rel_path("knowledge_attachments"),
                kb / vault_rel_path("knowledge_hubs"),
                auto / vault_rel_path("templates_root"),
                auto / vault_rel_path("templates_clones"),
            ]
        )
    if prof.module(MODULE_PLANNING):
        auto = root / folder("automation")
        paths.extend(
            [
                auto / vault_rel_path("templates_root"),
                auto / vault_rel_path("templates_v2"),
                auto / vault_rel_path("templates_entities"),
            ]
        )
    paths.append(root / ".sync")

    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def ensure_vault_layout(
    profile: Optional[CapabilityProfile] = None,
    vault_root: Optional[Path] = None,
) -> list[str]:
    """Create missing directories; return list of created paths."""
    created: list[str] = []
    for p in planned_vault_dirs(profile, vault_root):
        created.extend(_mkdir(p))
    return created
