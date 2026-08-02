"""Discover dashboard chart PNGs from vault_paths config + charts directory scan.

No filenames are hardcoded in Python — keys and relative paths come from
``config/vault_paths*.yaml``; filesystem scan only finds existing PNGs under
the configured charts root.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from shared.chart_paths import chart_path, charts_root
from shared.paths import vault_root_optional
from shared.vault_paths_config import finance_sub, folder, vault_paths_config


@dataclass(frozen=True)
class ChartEntry:
    key: str
    rel_path: str
    family: str
    exists: bool
    mtime_iso: str = ""
    size_bytes: int = 0


_FAMILY_RE = re.compile(r"^chart_([a-z0-9]+)_", re.IGNORECASE)


def _family_from_key(key: str) -> str:
    m = _FAMILY_RE.match(key or "")
    if m:
        return m.group(1).lower()
    return "other"


def _family_from_rel(rel: str) -> str:
    part = (rel or "").replace("\\", "/").split("/", 1)[0].strip()
    return part.lower() if part else "other"


def _stat(path: Path) -> tuple[bool, str, int]:
    if not path.is_file():
        return False, "", 0
    st = path.stat()
    ts = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return True, ts, int(st.st_size)


def _finance_chart_abs(vault: Path, rel_template: str) -> Path:
    """Resolve finance chart path under dashboards/charts (finance graphs subdir)."""
    from shared.vault_paths_config import dashboards_sub

    charts = vault / folder("dashboards") / dashboards_sub("charts")
    try:
        fin_sub = finance_sub("graphs_finance")
    except KeyError:
        fin_sub = ""
    rel = str(rel_template).lstrip("/")
    if fin_sub and not rel.lower().startswith(fin_sub.lower() + "/") and "/" not in rel:
        return charts / fin_sub / rel
    return charts / rel


def iter_config_chart_keys() -> list[tuple[str, str, str]]:
    """Return (key, source, rel_template) from vault_paths.

    source is ``files`` or ``finance``.
    """
    cfg = vault_paths_config()
    out: list[tuple[str, str, str]] = []
    files = cfg.get("files") if isinstance(cfg.get("files"), dict) else {}
    for key, template in files.items():
        k = str(key)
        if not k.startswith("chart_") or not k.endswith("_png"):
            continue
        out.append((k, "files", str(template)))
    finance = cfg.get("finance") if isinstance(cfg.get("finance"), dict) else {}
    for key, template in finance.items():
        k = str(key)
        if not k.startswith("chart_") or not k.endswith("_png"):
            continue
        out.append((k, "finance", str(template)))
    return out


def catalog_charts(
    vault: Path | None = None,
    *,
    query: str = "",
    family: str = "",
    only_existing: bool = False,
) -> list[ChartEntry]:
    """Build chart catalog: configured keys first, then unscanned PNGs under charts root."""
    root = vault or vault_root_optional()
    if root is None:
        return []

    q = (query or "").strip().lower()
    fam = (family or "").strip().lower()
    by_rel: dict[str, ChartEntry] = {}

    for key, source, template in iter_config_chart_keys():
        try:
            if source == "finance":
                abs_path = _finance_chart_abs(root, template)
            else:
                abs_path = chart_path(root, key)
        except Exception:
            continue
        try:
            rel = abs_path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        exists, mtime, size = _stat(abs_path)
        entry = ChartEntry(
            key=key,
            rel_path=rel,
            family=_family_from_key(key) if source == "files" else "finance",
            exists=exists,
            mtime_iso=mtime,
            size_bytes=size,
        )
        by_rel[rel] = entry

    try:
        croot = charts_root(root)
    except Exception:
        croot = None
    if croot and croot.is_dir():
        for path in sorted(croot.rglob("*.png")):
            try:
                rel = path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
            if rel in by_rel:
                continue
            exists, mtime, size = _stat(path)
            stem = path.stem.lower().replace(" ", "_")
            key = f"fs:{stem}"
            by_rel[rel] = ChartEntry(
                key=key,
                rel_path=rel,
                family=_family_from_rel(path.relative_to(croot).as_posix()),
                exists=exists,
                mtime_iso=mtime,
                size_bytes=size,
            )

    entries = list(by_rel.values())
    if only_existing:
        entries = [e for e in entries if e.exists]
    if fam:
        entries = [e for e in entries if fam in e.family or e.family.startswith(fam)]
    if q:
        entries = [
            e
            for e in entries
            if q in e.key.lower()
            or q in e.rel_path.lower()
            or q in e.family.lower()
            or q in Path(e.rel_path).stem.lower()
        ]
    entries.sort(key=lambda e: (not e.exists, e.family, e.key))
    return entries


def format_catalog(
    entries: list[ChartEntry],
    *,
    limit: int = 80,
    stale_hours: int = 0,
) -> str:
    if not entries:
        return ""
    now = datetime.now(timezone.utc)
    lines = []
    for e in entries[: max(1, limit)]:
        status = "ok" if e.exists else "missing"
        mtime = e.mtime_iso or "-"
        age_s = ""
        if e.exists and e.mtime_iso:
            try:
                ts = datetime.fromisoformat(e.mtime_iso.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_h = max(0.0, (now - ts).total_seconds() / 3600.0)
                age_s = f" age_h={age_h:.1f}"
                if stale_hours > 0 and age_h > stale_hours:
                    status = "stale"
            except ValueError:
                pass
        lines.append(
            f"{e.key} [{e.family}] {status} mtime={mtime}{age_s} path={e.rel_path}"
        )
    if len(entries) > limit:
        lines.append(f"... +{len(entries) - limit} more")
    return "\n".join(lines)
