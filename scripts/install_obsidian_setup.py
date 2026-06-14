#!/usr/bin/env python3
"""Install Obsidian plugins config, Templater scripts, and KB clone templates into the vault."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.capabilities.obsidian_vault_setup import install_obsidian_assets, required_plugins
from shared.capabilities.profile import clear_capabilities_cache, load_capabilities
from shared.paths import vault_root_optional
from shared.setup.load_env import load_repo_env

load_repo_env(_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default="", help="Override VAULT_PATH")
    parser.add_argument("--locale", default="", help="en or ru (default AGENT_LOCALE)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing template files")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-plugins", action="store_true", help="Print required Community plugins and exit")
    args = parser.parse_args()

    if args.vault:
        os.environ["VAULT_PATH"] = args.vault

    loc = args.locale.strip() if args.locale else None
    if args.list_plugins:
        for pid in required_plugins(loc):
            print(pid)
        return 0

    root = vault_root_optional()
    if root is None:
        print("Set VAULT_PATH in .env or pass --vault", file=sys.stderr)
        return 1

    clear_capabilities_cache()
    prof = load_capabilities()
    written = install_obsidian_assets(prof, root, locale=loc, force=args.force, dry_run=args.dry_run)
    if not written:
        print("obsidian setup: nothing to write (existing files or disabled modules)")
        return 0
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
