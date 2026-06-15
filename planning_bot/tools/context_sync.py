from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = PROJECT_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from planning_bot.core.pdmsg import pdmsg
from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_TODAY_JSON, CONTEXT_WEEK_JSON
from planning_bot.services.context_parser import (
    filter_logging_window,
    get_snapshots,
    snap_local_date,
    week_aggregates,
)
from planning_bot.services.reference_date import reference_now, reference_today

from planning_bot.services.iphone_snapshot_names import (
    is_canonical_filename,
    is_legacy_filename,
    needs_rename_filename,
)

CONTEXT_TTL_DAYS = 30

# (comment)
_GARBAGE_COMMA_DATE_TXT = re.compile(r"^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}\.txt$")


def _cleanup_data_dir_root(data_dir: Path) -> int:
    'Operation implementation.'
    if not data_dir.is_dir():
        return 0
    deleted = 0
    for path in data_dir.iterdir():
        if not path.is_file():
            continue
        nm = path.name
        kill = (
            nm == pdmsg("auto_af0f6aa432")
            or bool(_GARBAGE_COMMA_DATE_TXT.match(nm))
            or (nm.startswith(pdmsg("auto_eb22b2c9df")) and nm.endswith(".txt"))
        )
        if kill:
            try:
                path.unlink()
                deleted += 1
                logger.info(pdmsg("auto_41a1403fc4"), nm)
            except Exception as e:
                logger.warning(pdmsg("auto_56012e66af"), path, e)
    return deleted


def _cleanup_mac_misfires(mac_dir: Path) -> int:
    'Operation implementation.'
    if not mac_dir.exists():
        return 0
    deleted = 0
    for path in mac_dir.glob("*.txt"):
        nm = path.name
        ok = is_canonical_filename(nm) or needs_rename_filename(nm)
        if ok:
            continue
        try:
            path.unlink()
            deleted += 1
            logger.info(pdmsg("auto_85f9559eb7"), nm)
        except Exception as e:
            logger.warning(pdmsg("auto_56012e66af"), path, e)
    return deleted


def _cleanup_old_context_files(mac_dir: Path) -> int:
    'Operation implementation.'
    if not mac_dir.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=CONTEXT_TTL_DAYS)
    deleted = 0
    candidates = list(mac_dir.glob(pdmsg("auto_8ebed9299d")))
    candidates += [
        p
        for p in mac_dir.glob("*.txt")
        if is_canonical_filename(p.name) or is_legacy_filename(p.name)
    ]
    seen: set[str] = set()
    for path in candidates:
        rp = str(path.resolve())
        if rp in seen:
            continue
        seen.add(rp)
        if "{" in path.name:
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if mtime < cutoff:
                path.unlink()
                deleted += 1
                logger.info(pdmsg("auto_1b3ad4edf5"), path.name)
        except Exception as e:
            logger.warning(pdmsg("auto_56012e66af"), path.name, e)
    return deleted


def _rename_legacy_mac_snapshots(mac_dir: Path) -> int:
    """DD.MM.YYYY, HH:MM.txt → YYYY-MM-DD, HH-MM.txt (Mac Shortcut still emits legacy names)."""
    from planning_bot.services.action_snapshot_rename import (
        rename_snapshot_dir,
        vault_root_from_actions_dir,
    )
    from planning_bot.services.context_parser import parse_context_file
    from planning_bot.services.iphone_snapshot_names import parse_filename_ts

    def _resolve_ts(path: Path) -> datetime | None:
        snaps = parse_context_file(path)
        if snaps:
            try:
                return datetime.fromisoformat(str(snaps[0]["ts"]))
            except ValueError:
                pass
        return parse_filename_ts(path.name)

    vault = vault_root_from_actions_dir(mac_dir)
    result = rename_snapshot_dir(
        snapshot_dir=mac_dir,
        vault=vault,
        resolve_ts=_resolve_ts,
        apply=True,
        label="mac",
    )
    renamed = int(result.get("renamed") or 0)
    if renamed:
        logger.info("Renamed %s legacy Mac snapshot file(s) to canonical names", renamed)
    return renamed


def run_context_sync() -> bool:
    try:
        CONTEXT_MAC_DIR.mkdir(parents=True, exist_ok=True)
        data_root = CONTEXT_MAC_DIR.parent.parent  # (comment)

        _rename_legacy_mac_snapshots(CONTEXT_MAC_DIR)
        n_root = _cleanup_data_dir_root(data_root)
        n_mac = _cleanup_mac_misfires(CONTEXT_MAC_DIR)
        n_old = _cleanup_old_context_files(CONTEXT_MAC_DIR)
        n_del = n_root + n_mac + n_old
        if n_del:
            print(
                pdmsg("auto_8e44dcce79", n_del=n_del, n_root=n_root, n_mac=n_mac, n_old=n_old),
                flush=True,
            )

        snaps_week_raw = get_snapshots(CONTEXT_MAC_DIR, days=7, logging_window_only=False)
        snaps_week = filter_logging_window(snaps_week_raw)
        ref = reference_today()
        yday = ref - timedelta(days=1)
        snaps_today = [
            s
            for s in snaps_week
            if (sd := snap_local_date(s)) is not None and sd in (ref, yday)
        ]

        CONTEXT_TODAY_JSON.parent.mkdir(parents=True, exist_ok=True)
        payload_today = {
            "meta": {
                "updated_at": reference_now().isoformat(timespec="seconds"),
                "anchor_date": ref.isoformat(),
                "local_dates_included": [ref.isoformat(), yday.isoformat()],
                "note": pdmsg("auto_4d250494e9"),
                "logging_window_hours": "10:00–02:00",
                "snaps_today_in_window": len(snaps_today),
                "snaps_week_in_window": len(snaps_week),
                "snaps_week_all": len(snaps_week_raw),
                "ttl_days": CONTEXT_TTL_DAYS,
            },
            "today": snaps_today,
            "recent": snaps_week[-20:],
        }
        CONTEXT_TODAY_JSON.write_text(
            json.dumps(payload_today, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        agg = week_aggregates(snaps_week)
        payload_week = {
            "meta": {
                "updated_at": reference_now().isoformat(timespec="seconds"),
                "logging_window_hours": "10:00–02:00",
                "ttl_days": CONTEXT_TTL_DAYS,
                **{k: v for k, v in agg.items() if k != "count"},
                "snapshot_count": agg.get("count", 0),
            },
            "snapshots": snaps_week,
        }
        CONTEXT_WEEK_JSON.write_text(
            json.dumps(payload_week, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            pdmsg("auto_cf57392f53", _p1=len(snaps_today), _p3=len(snaps_week), _p5=len(snaps_week_raw)),
            flush=True,
        )
        return True
    except Exception as e:
        logger.error(pdmsg("auto_24f969f593"), e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if run_context_sync() else 1)
