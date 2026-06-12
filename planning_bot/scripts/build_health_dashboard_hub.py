#!/usr/bin/env python3
"""Write 🏥 health hub markdown from locale config (not overwritten by nutrition chart)."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from planning_bot.core.pdmsg import pdmsg
from shared.vault_paths_config import folder, vault_file


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / folder("tasks")).is_dir() and (p / folder("dashboards")).is_dir():
            return p
    return start.parents[3]


def main() -> int:
    os.environ.pop("PYTHONPATH", None)
    from shared.domain_messages import clear_domain_messages_cache
    from shared.locale import agent_locale

    clear_domain_messages_cache()
    agent_locale()
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=str)
    args = ap.parse_args()
    vault = Path(args.vault).resolve() if args.vault else _discover_vault(Path(__file__).resolve())
    hub = vault / folder("dashboards") / vault_file("health_dashboard_md")
    body = pdmsg("health_dashboard_hub")
    if not body.strip():
        return 1
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "{updated}" in body:
        body = body.replace("{updated}", ts)
    hub.parent.mkdir(parents=True, exist_ok=True)
    hub.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
    print(f"OK: {hub}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
