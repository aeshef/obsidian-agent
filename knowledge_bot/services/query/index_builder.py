from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("kb.query.index")

_DEFAULT_INDEX_FIELDS = ["city", "category", "address"]


def index_extra_fields() -> list[str]:
    from shared.agent.platform_config import platform_str_list

    return platform_str_list(
        "knowledge_query",
        "index_extra_fields",
        env="KNOWLEDGE_INDEX_EXTRA_FIELDS",
        default=_DEFAULT_INDEX_FIELDS,
    )


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def index_json_path() -> Path:
    d = _package_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "notes_index.json"


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    try:
        fm = yaml.safe_load(parts[1]) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    body = parts[2].lstrip("\n")
    return fm, body


def _preview_body(body: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(body) <= max_chars:
        return body, False
    return body[:max_chars], True


from shared.vault_layout import knowledge_attachments_subdir

SKIP_DIR_NAMES = {
    knowledge_attachments_subdir(),
    "Export",
    ".obsidian",
    ".git",
    "_index",
    ".rsync-backup",
}


def _iter_note_files(base: Path) -> list[Path]:
    out: list[Path] = []
    if not base.is_dir():
        return out
    for p in base.rglob("*.md"):
        try:
            rel = p.relative_to(base)
        except ValueError:
            continue
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        out.append(p)
    return sorted(out)


def _entry_from_path(
    vault_path: Path, path: Path, *, preview_cap: int
) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.warning("skip read %s: %s", path, e)
        return None
    fm, body = _parse_frontmatter(raw)
    rel = path.relative_to(vault_path).as_posix()
    title = fm.get("title")
    if not isinstance(title, str) or not title.strip():
        title = path.stem.replace("_", " ")
    ntype = fm.get("type")
    if not isinstance(ntype, str) or not ntype.strip():
        ntype = "?"
    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    elif not isinstance(tags, list):
        tags = []
    summary = fm.get("summary")
    if not isinstance(summary, str):
        summary = ""
    preview, truncated = _preview_body(body, preview_cap)
    extra: dict[str, Any] = {}
    for key in index_extra_fields():
        val = fm.get(key)
        if isinstance(val, str) and val.strip():
            extra[key] = val.strip()
    return {
        "rel_path": rel,
        "type": ntype.strip(),
        "title": title.strip(),
        "tags": [str(t) for t in tags],
        "summary": summary,
        "preview": preview,
        "preview_truncated": truncated,
        "mtime": path.stat().st_mtime,
        **extra,
    }


def build_index(vault_path: Path) -> dict[str, Any]:
    """Full scan of knowledge index roots: metadata + body preview for selection."""
    from shared.vault_layout import knowledge_index_roots

    roots = knowledge_index_roots()
    preview_cap = int(os.environ.get("KNOWLEDGE_SELECT_PREVIEW_CHARS", "12000"))
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        base = vault_path / root
        if not base.is_dir():
            log.warning("index root missing, skip: %s", base)
            continue
        for path in _iter_note_files(base):
            entry = _entry_from_path(vault_path, path, preview_cap=preview_cap)
            if entry is None:
                continue
            rel = entry["rel_path"]
            if rel in seen:
                continue
            seen.add(rel)
            entries.append(entry)
    return {
        "generated_at": time.time(),
        "vault": str(vault_path.resolve()),
        "index_roots": list(roots),
        "index_fields": list(index_extra_fields()),
        "count": len(entries),
        "entries": entries,
    }


def index_max_age() -> float:
    from shared.agent.platform_config import platform_float

    return platform_float(
        "knowledge_query",
        "index_max_age_sec",
        env="KNOWLEDGE_INDEX_MAX_AGE_SEC",
        default=3600.0,
    )


def index_needs_refresh(vault_path: Path) -> bool:
    from shared.vault_layout import knowledge_index_roots

    p = index_json_path()
    if not p.exists():
        return True
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        stored = raw.get("vault")
        if stored and Path(stored).resolve() != Path(vault_path).resolve():
            log.info("index was built for another vault, rebuilding")
            return True
        stored_roots = raw.get("index_roots")
        current_roots = knowledge_index_roots()
        if stored_roots != current_roots:
            log.info("index roots changed (%s -> %s), rebuilding", stored_roots, current_roots)
            return True
        stored_fields = raw.get("index_fields") or []
        current_fields = index_extra_fields()
        if list(stored_fields) != list(current_fields):
            log.info("index fields changed (%s -> %s), rebuilding", stored_fields, current_fields)
            return True
    except Exception:
        return True
    if index_max_age() <= 0:
        return True
    try:
        age = time.time() - p.stat().st_mtime
    except OSError:
        return True
    return age > index_max_age()


def build_or_refresh_index(vault_path: Path, *, force: bool = False) -> dict[str, Any]:
    if not force and not index_needs_refresh(vault_path):
        return load_index()
    log.info("building knowledge index under %s", vault_path)
    data = build_index(vault_path)
    outp = index_json_path()
    tmp = outp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(outp)
    log.info("knowledge index written: %d notes -> %s", data["count"], outp)
    try:
        from knowledge_bot.services.query.dense_index import sync_from_index

        sync_from_index(data, blocking=True if force else None)
    except Exception:
        log.exception("dense index sync skipped")
    return data


def load_index() -> dict[str, Any]:
    p = index_json_path()
    if not p.exists():
        return {"generated_at": 0, "vault": "", "count": 0, "entries": []}
    return json.loads(p.read_text(encoding="utf-8"))


def schedule_rebuild_if_enabled(vault_path: Path) -> None:
    if os.environ.get("KNOWLEDGE_REBUILD_ON_SAVE", "").strip() != "1":
        return
    import threading

    def _job() -> None:
        try:
            build_or_refresh_index(vault_path, force=True)
        except Exception:
            log.exception("background index rebuild failed")

    threading.Thread(target=_job, daemon=True).start()
