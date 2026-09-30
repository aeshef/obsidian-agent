"""Read sync markers by operation time, independent of filesystem copy times."""
import json
from pathlib import Path
from datetime import datetime

def _safe_read(path, limit=None):
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""

def _age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        # A copied marker's mtime is not the time of the successful operation.
        raw = path.read_text().strip().split()[0]
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        now = datetime.now(stamp.tzinfo)
        age = (now - stamp).total_seconds() / 3600
        return age if age >= 0 else None
    except (OSError, ValueError, IndexError):
        return None


def _pipeline_problems(sync_dir: Path) -> list[str]:
    problems = []
    failed = sync_dir / "last_sync_failed.txt"
    ok = sync_dir / "last_sync_ok.txt"
    failed_parts = _safe_read(failed).split()
    if failed_parts and (not ok.exists() or failed_parts[0] > _safe_read(ok).strip()):
        problems.append(_safe_read(failed, 300).strip())
    path = sync_dir / "pipeline_health.json"
    try:
        data = json.loads(path.read_text())
        stamp = datetime.fromisoformat(data["checked_at"].replace("Z", "+00:00"))
        if (datetime.now(stamp.tzinfo) - stamp).total_seconds() > 86400:
            problems.append("pipeline_health: stale")
        if data.get("status") != "ok":
            problems.extend(f"{name}: {value.get('status', 'unknown')}" for name, value in data.get("sources", {}).items() if value.get("status") != "ok")
            problems.extend(f"{name}: {value.get('status', 'unknown')}" for name, value in data.get("dependencies", {}).items())
            problems.append("pipeline_health: " + str(data.get("status", "unknown")))
    except (OSError, ValueError, KeyError, TypeError):
        problems.append("pipeline_health: missing/invalid")
    return problems

