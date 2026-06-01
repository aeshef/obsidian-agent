from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# (comment)
from planning_bot.core.pdmsg import pdmsg
LEGACY_FILENAME_RE = re.compile(
    r"^(\d{2})\.(\d{2})\.(\d{4}), (\d{2}):(\d{2})(?:\s+copy)?\.txt$",
    re.IGNORECASE,
)
# (comment)
CANONICAL_FILENAME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2}), (\d{2})-(\d{2})(?:_\d+)?\.txt$",
)
KONTEXT_PREFIX_RE = re.compile(pdmsg("auto_86a3ff42a2"), re.IGNORECASE)


def normalize_snapshot_basename(name: str) -> str:
    'Operation implementation.'
    return re.sub(r"\s+copy(?=\.txt$)", "", name, flags=re.IGNORECASE)


def parse_filename_ts(filename: str) -> Optional[datetime]:
    'Operation implementation.'
    base = normalize_snapshot_basename(filename.strip())
    km = KONTEXT_PREFIX_RE.match(base)
    if km:
        from planning_bot.services.context_parser import _parse_ts as parse_mac_ts

        return parse_mac_ts(km.group(1).strip())
    m = LEGACY_FILENAME_RE.match(base)
    if m:
        d, mo, y, h, mi = m.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(h), int(mi))
        except ValueError:
            return None
    m = CANONICAL_FILENAME_RE.match(base)
    if m:
        y, mo, d, h, mi = m.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(h), int(mi))
        except ValueError:
            return None
    return None


def is_canonical_filename(filename: str) -> bool:
    base = normalize_snapshot_basename(filename.strip())
    return bool(CANONICAL_FILENAME_RE.match(base)) and not LEGACY_FILENAME_RE.match(base)


def is_legacy_filename(filename: str) -> bool:
    base = normalize_snapshot_basename(filename.strip())
    return bool(LEGACY_FILENAME_RE.match(base))


def needs_rename_filename(filename: str) -> bool:
    'Operation implementation.'
    base = normalize_snapshot_basename(filename.strip())
    if is_canonical_filename(base):
        return False
    if is_legacy_filename(base):
        return True
    if KONTEXT_PREFIX_RE.match(base):
        return True
    return False


def format_snapshot_filename(dt: datetime, *, suffix: str = "") -> str:
    'Operation implementation.'
    core = f"{dt.strftime('%Y-%m-%d')}, {dt.strftime('%H-%M')}"
    if suffix:
        return f"{core}_{suffix}.txt"
    return f"{core}.txt"
