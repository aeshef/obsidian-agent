#!/usr/bin/env python3
"""Write system hub markdown — agent cost + audits."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _bootstrap_path() -> None:
    env = (os.environ.get("AGENT_ROOT") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    try:
        here = Path(__file__)
        if here.is_file():
            candidates.append(here.resolve().parents[2])
    except Exception:
        pass
    cwd = Path.cwd()
    if (cwd / "core").is_dir():
        candidates.append(cwd.parent)
    candidates.append(cwd)
    for c in candidates:
        if (c / "shared").is_dir() and (c / "planning_bot").is_dir():
            s = str(c.resolve())
            if s not in sys.path:
                sys.path.insert(0, s)
            return


_bootstrap_path()

from planning_bot.core.pdmsg import pdmsg
from shared.analytics.system_hub_layout import render_system_hub
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
    from shared.tz import now_in_tz

    vault = Path(args.vault).resolve() if args.vault else _discover_vault(Path.cwd())
    ts = now_in_tz().strftime("%Y-%m-%d %H:%M")
    body = render_system_hub(vault, ts=ts, msg=pdmsg)
    hub = vault / folder("dashboards") / vault_file("system_hub_md")
    hub.parent.mkdir(parents=True, exist_ok=True)
    hub.write_text(body, encoding="utf-8")
    print(f"OK: {hub}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
