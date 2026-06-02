from planning_bot.core.config import ACTION_LOG_PREFIX, DONE_COLUMN, GRAPHICS_DIR
from planning_bot.core.pdmsg import pdmsg
from planning_bot.scripts.vault_discover import discover_vault
from shared.vault_paths_config import vault_file

#!/usr/bin/env python3
"""Planning bot vault maintenance script."""
import argparse
import sys
from pathlib import Path

LOG_PREFIX = ACTION_LOG_PREFIX


def main():
    ap = argparse.ArgumentParser(description="Planning bot maintenance utility")
    ap.add_argument("--vault", type=Path, default=None, help=pdmsg("auto_14cbadfca6"))
    ap.add_argument("--dry-run", action="store_true", help=pdmsg("auto_3d853f908d"))
    args = ap.parse_args()

    if args.vault:
        dash = Path(args.vault) / pdmsg("auto_1c7277d3a5")
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from planning_bot.core.config import LOGS_DIR
        dash = LOGS_DIR

    if not dash.is_dir():
        print(pdmsg("auto_a9cfe5780b", _p1=dash), flush=True)
        return 1

    # (comment)
    removed = []
    for f in dash.glob(f"{LOG_PREFIX}*.md"):
        if f.parent != dash:
            continue
        if args.dry_run:
            print(pdmsg("auto_97aa50a756", _p1=f), flush=True)
        else:
            f.unlink()
            print(pdmsg("auto_07438bbfa5", _p1=f), flush=True)
        removed.append(f.name)

    if not removed:
        print(pdmsg("auto_a0815d49a8"), flush=True)
    elif not args.dry_run:
        print(pdmsg("auto_4c1afa777b", _p1=len(removed)), flush=True)
        print(pdmsg("auto_b5a8823167"), flush=True)
        print(pdmsg("auto_77bc971bec"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
