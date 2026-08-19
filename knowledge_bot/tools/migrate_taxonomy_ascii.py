#!/usr/bin/env python3
"""Idempotent ASCII taxonomy: category facet + topic/technology → domain/tech.

  python tools/migrate_taxonomy_ascii.py
  python tools/migrate_taxonomy_ascii.py --apply
  python tools/migrate_taxonomy_ascii.py --apply --vault /path/to/vault
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_bot.core.config import load_config
from knowledge_bot.services.tag_remap import apply_taxonomy_ascii


def main() -> int:
    argv = sys.argv[1:]
    if "--vault" in argv:
        i = argv.index("--vault")
        if i + 1 < len(argv):
            import os

            os.environ["VAULT_PATH"] = argv[i + 1]
    cfg = load_config()
    do_write = "--apply" in argv
    st = apply_taxonomy_ascii(cfg.vault_path, dry_run=not do_write)
    print(st)
    return 0 if st.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
