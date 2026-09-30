"""Daily metric-group revisions, independently dated from their export time."""
import math
from datetime import date, datetime, timezone

from shared.agent.config import agent_config_dir
from shared.yaml_config import load_merged_config

META = frozenset({"schema_version", "measurement_day", "captured_at", "metric_group", "read_status", "empty_fields", "_revisions"})


def groups():
    return load_merged_config(str(agent_config_dir()), "health_backfill").get("groups", {})


def validate(row):
    if str(row.get("schema_version", "")) not in {"2", "2.0"}:
        return False
    try:
        date.fromisoformat(row["measurement_day"])
        ts = datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
        if ts.tzinfo is None or (ts-datetime.now(timezone.utc)).total_seconds() > 300:
            return False
        group = row["metric_group"]
        allowed = set(groups()[group])
        empty = {v.strip() for v in str(row.get("empty_fields", "")).split(",") if v.strip()}
        measured = date.fromisoformat(row["measurement_day"])
        if measured > ts.date():
            return False
        supplied = set(row) & allowed
        for field in supplied - {"sleep_interval", "sleep_detail"}:
            value = float(row[field])
            if not math.isfinite(value) or value < 0:
                return False
        return row.get("read_status") == "ok" and empty <= allowed and not (empty & supplied) and bool(supplied or empty)
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def merge(current, candidate):
    out = dict(current or {})
    revisions = dict(out.get("_revisions", {}))
    group = candidate["metric_group"]
    captured = candidate["captured_at"]
    def instant(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if group in revisions and instant(captured) <= instant(revisions[group]):
        return out
    # Each group is a complete replacement for the explicitly exported fields only.
    # An unavailable/empty reading becomes unknown, never zero.
    empty = {v.strip() for v in str(candidate.get("empty_fields", "")).split(",") if v.strip()}
    for key in groups()[group]:
        if key in empty:
            out[key] = None
        elif key in candidate:
            out[key] = candidate[key]
    revisions[group] = captured
    out.update(ts=candidate["measurement_day"]+"T00:00:00", source="iphone_backfill_v2",
               measurement_day=candidate["measurement_day"], _revisions=revisions,
               captured_at=max(revisions.values(), key=instant))
    return out
