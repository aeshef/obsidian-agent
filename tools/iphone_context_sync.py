from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
from planning_bot.core.pdmsg import pdmsg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = PROJECT_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from planning_bot.core.config import IPHONE_CONTEXT_DIR, IPHONE_TODAY_JSON, IPHONE_WEEK_JSON
from planning_bot.services.iphone_context_parser import (
    discover_numeric_keys,
    get_snapshots,
    parse_iphone_file,
    week_numeric_aggregates,
)
from planning_bot.services.iphone_health_fields import is_valid_health_snapshot


def _snap_local_date(snap: dict) -> Optional[date]:
    'Operation implementation.'
    try:
        return datetime.fromisoformat(str(snap.get("ts", ""))).date()
    except (TypeError, ValueError):
        return None


def _cleanup_invalid_iphone_txt_files() -> int:
    deleted = 0
    for path in IPHONE_CONTEXT_DIR.glob("*.txt"):
        if path.name.startswith("."):
            continue
        snap = parse_iphone_file(path)
        if snap is not None and is_valid_health_snapshot(snap):
            continue
        try:
            path.unlink()
            deleted += 1
            logger.info(pdmsg("auto_8b2d0f6a91"), path.name)
        except OSError as e:
            logger.warning(pdmsg("auto_7a1c9e5b80"), path.name, e)
    return deleted


def run_iphone_context_sync() -> bool:
    try:
        IPHONE_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)

        n_garbage = _cleanup_invalid_iphone_txt_files()
        if n_garbage:
            print(pdmsg("auto_9c3e1a7b42", _p1=n_garbage), flush=True)

        snaps_week = get_snapshots(IPHONE_CONTEXT_DIR, days=7)
        # (comment)
        d0 = date.today()
        d1 = d0 - timedelta(days=1)
        snaps_today = [
            s
            for s in snaps_week
            if (sd := _snap_local_date(s)) is not None and sd in (d0, d1)
        ]

        IPHONE_TODAY_JSON.parent.mkdir(parents=True, exist_ok=True)

        agg_week = week_numeric_aggregates(snaps_week)
        agg_today = week_numeric_aggregates(snaps_today)

        payload_today = {
            "meta": {
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "source_dir": str(IPHONE_CONTEXT_DIR),
                "local_dates_included": [d0.isoformat(), d1.isoformat()],
                "note": pdmsg("auto_4d250494e9"),
                "snaps_today": len(snaps_today),
                "snaps_week": len(snaps_week),
                "aggregates_today": {k: v for k, v in agg_today.items() if k != "snapshot_count"},
            },
            "today": snaps_today,
            "recent": snaps_week[-20:],
        }
        IPHONE_TODAY_JSON.write_text(
            json.dumps(payload_today, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        payload_week = {
            "meta": {
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "source_dir": str(IPHONE_CONTEXT_DIR),
                "snapshot_count": len(snaps_week),
                "numeric_fields": discover_numeric_keys(snaps_week),
                "aggregates_week": {k: v for k, v in agg_week.items() if k != "snapshot_count"},
            },
            "snapshots": snaps_week,
        }
        IPHONE_WEEK_JSON.write_text(
            json.dumps(payload_week, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(
            pdmsg("auto_75c42fc423", _p1=len(snaps_today), _p3=len(snaps_week)),
            flush=True,
        )
        return True
    except Exception as e:
        logger.error(pdmsg("auto_55744c9550"), e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if run_iphone_context_sync() else 1)
