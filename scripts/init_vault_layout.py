#!/usr/bin/env python3
"""Create vault directories for the active capabilities profile (idempotent)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.agent.config import agent_config_dir
from shared.capabilities.profile import clear_capabilities_cache, load_capabilities
from shared.setup.load_env import load_repo_env

load_repo_env(_ROOT)
from shared.capabilities.vault_init import ensure_vault_layout, planned_vault_dirs
from shared.paths import vault_root_optional


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default="", help="Override VAULT_PATH")
    parser.add_argument("--dry-run", action="store_true", help="List dirs only, do not mkdir")
    parser.add_argument(
        "--allow-missing-capabilities",
        action="store_true",
        help="Allow run without capabilities.yaml (author full install; not for OSS onboarding)",
    )
    args = parser.parse_args()

    if args.vault:
        os.environ["VAULT_PATH"] = args.vault
    root = vault_root_optional()
    if root is None:
        print("Set VAULT_PATH in .env or pass --vault", file=sys.stderr)
        return 1

    cap_file = agent_config_dir() / "capabilities.yaml"
    if not cap_file.is_file() and not args.allow_missing_capabilities:
        print(
            "capabilities.yaml missing — all modules would be enabled (wrong folders for finance/planning-only).\n"
            "Run: python3 scripts/apply_capabilities_profile.py --preset <name> --write --patch-env\n"
            "Or pass --allow-missing-capabilities only on the author full-install machine.",
            file=sys.stderr,
        )
        return 2

    clear_capabilities_cache()
    prof = load_capabilities()
    planned = planned_vault_dirs(prof, root)
    if args.dry_run:
        for p in planned:
            print(p)
        return 0

    created = ensure_vault_layout(prof, root)
    if created:
        print(f"Created {len(created)} directories under {root}")
        for c in created:
            print(f"  + {c}")
    else:
        print(f"Vault layout OK ({len(planned)} dirs checked) under {root}")

    from shared.capabilities.vault_paths_locale import cleanup_ghost_locale_folders

    for line in cleanup_ghost_locale_folders(root):
        print(f"  ghost: {line}")

    from shared.capabilities.vault_dashboard_scaffold import scaffold_vault_dashboards

    dashed = scaffold_vault_dashboards(prof, root)
    for p in dashed:
        print(f"  dashboard: {p}")

    from shared.capabilities.vault_routines_scaffold import scaffold_vault_routines

    routines = scaffold_vault_routines(prof, root)
    for p in routines:
        print(f"  routines: {p}")

    from shared.capabilities.obsidian_vault_setup import install_obsidian_assets

    obsidian = install_obsidian_assets(prof, root)
    for p in obsidian:
        print(f"  obsidian: {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
