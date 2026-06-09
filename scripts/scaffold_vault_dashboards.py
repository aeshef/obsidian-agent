#!/usr/bin/env python3
"""Scaffold Obsidian dashboard markdown (module-aware, locale from AGENT_LOCALE)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.capabilities.profile import clear_capabilities_cache, load_capabilities
from shared.capabilities.vault_dashboard_scaffold import scaffold_vault_dashboards
from shared.paths import vault_root_optional
from shared.setup.load_env import load_repo_env

load_repo_env(_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default="", help="Override VAULT_PATH")
    parser.add_argument("--locale", default="", help="en or ru (default AGENT_LOCALE)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite existing dashboard files")
    args = parser.parse_args()

    if args.vault:
        os.environ["VAULT_PATH"] = args.vault
    root = vault_root_optional()
    if root is None:
        print("Set VAULT_PATH in .env or pass --vault", file=sys.stderr)
        return 1

    clear_capabilities_cache()
    prof = load_capabilities()
    loc = args.locale.strip() if args.locale else None
    written = scaffold_vault_dashboards(
        prof,
        root,
        locale=loc,
        dry_run=args.dry_run,
        force=args.force,
    )
    if not written:
        print("vault dashboards: nothing to write (existing files or no modules)")
        return 0
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
