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
from shared.vault_paths_config import dashboards_sub, finance_sub, folder, vault_rel_path


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
        paths.extend(
            [
                root / folder("tasks"),
                root / folder("goals"),
                root / folder("routines"),
                root / folder("handwritten"),
                data_dir / vault_rel_path("actions_mac"),
                data_dir / vault_rel_path("actions_iphone"),
            ]
        )
    if prof.module(MODULE_FINANCE) and needs_dash:
        paths.append((root / folder("dashboards") / dashboards_sub("charts")) / finance_sub("graphs_finance"))
    if prof.module(MODULE_KNOWLEDGE):
        kb = root / knowledge_subdir()
        paths.extend([kb, kb / vault_rel_path("knowledge_attachments"), kb / vault_rel_path("knowledge_hubs")])
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
