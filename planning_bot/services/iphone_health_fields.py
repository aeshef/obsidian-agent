from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Sequence

from shared.agent.config import load_health_parse_config
from shared.parsing.datetime_parse import parse_datetime
from shared.parsing.snapshot_kv import extract_kv_fields, safe_float

META_KEYS = frozenset({"ts", "source"})

# Keys produced when clipboard/HTML/CSS or email footers are parsed as key: value
_SPAM_FIELD_KEYS = frozenset({
    "https",
    "http",
    "unsubscribe",
    "help",
    "margin",
    "padding",
    "display",
    "border",
    "outline",
    "cursor",
    "width",
    "height",
    "color",
    "important",
})

_SPAM_VALUE_MARKERS = (
    "linkedin.com",
    "ozone.ru",
    "myaccount.google.com/notifications",
    "display: none",
    "email_job_alert",
)

# At least one numeric Health metric (after alias normalization)
_CORE_HEALTH_KEYS = frozenset({
    "steps",
    "resting_hr_bpm",
    "weight_kg",
    "hrv_ms",
    "calories_kcal",
    "active_calories_kcal",
    "heartbeat_load",
})


def _cfg() -> dict:
    return load_health_parse_config()


def shortcut_aliases() -> Dict[str, str]:
    raw = _cfg().get("shortcut_aliases") or {}
    return {str(k).lower(): str(v) for k, v in raw.items()}


def string_keys() -> frozenset[str]:
    return frozenset(str(k) for k in (_cfg().get("string_keys") or []))


def mail_ts_formats() -> tuple[str, ...]:
    return tuple(str(f) for f in (_cfg().get("mail_ts_formats") or []))


def file_ts_formats() -> tuple[str, ...]:
    return tuple(str(f) for f in (_cfg().get("file_ts_formats") or []))


def parse_ts(s: str, *, formats: tuple[str, ...] | None = None) -> Optional[datetime]:
    return parse_datetime(s, strptime_formats=formats or mail_ts_formats())


def extract_raw_fields(text: str) -> Dict[str, str]:
    # sleep_detail may span multiple lines (stage breakdown after Total Time Asleep).
    return extract_kv_fields(text, multiline_keys=frozenset({"sleep", "sleep_detail"}))


def is_numeric_snapshot_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return safe_float(value) is not None
    return False


def _field_values_text(snap: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key, value in snap.items():
        if key in META_KEYS or value is None:
            continue
        parts.append(str(key))
        parts.append(str(value))
    return "\n".join(parts).lower()


def is_valid_health_snapshot(snap: Mapping[str, Any] | None) -> bool:
    """True only for real Shortcuts/Health exports (not CSS, URLs, mail footers)."""
    if not snap:
        return False

    keys = {str(k).lower() for k in snap.keys()}
    if keys & _SPAM_FIELD_KEYS:
        return False

    blob = _field_values_text(snap)
    if any(marker in blob for marker in _SPAM_VALUE_MARKERS):
        return False

    if snap.get("sleep_interval") or snap.get("sleep_detail"):
        return True

    if any(snap.get(k) is not None for k in _CORE_HEALTH_KEYS):
        numeric = discover_numeric_keys([snap])
        return len(numeric) >= 1

    return False


def health_snapshot_score(snap: Mapping[str, Any]) -> int:
    """Higher = richer Health snapshot (for picking one file per calendar day)."""
    if not is_valid_health_snapshot(snap):
        return -1
    score = len(discover_numeric_keys([snap])) * 2
    if snap.get("sleep_interval"):
        score += 12
    if snap.get("sleep_detail"):
        score += 6
    return score


def discover_text_field_keys(snaps: Sequence[Mapping[str, Any]]) -> list[str]:
    """String metrics from health_parse string_keys (sleep, note, …) present in snaps."""
    sk = string_keys()
    found: set[str] = set()
    for snap in snaps:
        for key in sk:
            if snap.get(key) not in (None, ""):
                found.add(key)
    return sorted(found)


def discover_numeric_keys(snaps: Sequence[Mapping[str, Any]]) -> list[str]:
    found: set[str] = set()
    sk = string_keys()
    for snap in snaps:
        for key, value in snap.items():
            if key in META_KEYS or key in sk:
                continue
            if is_numeric_snapshot_value(value):
                found.add(key)
    return sorted(found)


def normalize_raw_fields(
    fields: Dict[str, str],
    *,
    fallback_ts: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    if not fields:
        return None

    aliases = shortcut_aliases()
    sk = string_keys()

    ts_raw = fields.get("ts") or ""
    ts = parse_ts(ts_raw) if ts_raw else None
    if ts is None:
        ts = fallback_ts
    if ts is None:
        return None

    result: Dict[str, Any] = {
        "ts": ts.strftime("%d.%m.%Y, %H:%M"),
        "source": "iphone",
    }

    sleep_raw = (fields.get("sleep") or "").strip()
    if sleep_raw:
        sleep_lines = sleep_raw.splitlines()
        result["sleep_interval"] = sleep_lines[0].strip()
        if len(sleep_lines) > 1:
            result["sleep_detail"] = "\n".join(sleep_lines[1:]).strip()

    for raw_key, raw_val in fields.items():
        if raw_key in ("ts", "sleep"):
            continue
        if not (raw_val or "").strip():
            continue
        norm_key = aliases.get(raw_key, raw_key)
        if norm_key in sk:
            result[norm_key] = raw_val.strip()
            continue
        fv = safe_float(raw_val)
        if fv is not None:
            result[norm_key] = fv
        else:
            result[norm_key] = raw_val.strip()

    return result
