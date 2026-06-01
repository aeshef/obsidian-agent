from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from planning_bot.services.iphone_snapshot_names import (
    format_snapshot_filename,
    is_canonical_filename,
    is_legacy_filename,
    needs_rename_filename,
    parse_filename_ts,
)

_COPY_SUFFIX = re.compile(r"\s+copy\.txt$", re.IGNORECASE)
# (comment)
_NUMERIC_DUP_SUFFIX = re.compile(r"^(\d{4}-\d{2}-\d{2}, \d{2}-\d{2})_(\d+)\.txt$")


def vault_root_from_actions_dir(actions_subdir: Path) -> Path:
    'Operation implementation.'
    return actions_subdir.resolve().parents[3]


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel_vault(vault: Path, path: Path) -> str:
    return str(path.resolve().relative_to(vault.resolve()))


def rename_snapshot_dir(
    *,
    snapshot_dir: Path,
    vault: Path,
    resolve_ts: Callable[[Path], datetime | None],
    apply: bool,
    label: str,
    verbose: bool = False,
) -> dict[str, Any]:
    snapshot_dir = snapshot_dir.resolve()
    vault = vault.resolve()
    if not snapshot_dir.is_dir():
        return {
            "ok": True,
            "label": label,
            "renamed": 0,
            "removed": 0,
            "errors": [],
            "unlink_on_server": [],
        }

    plans: list[tuple[Path, Path, str]] = []
    errors: list[str] = []
    used_names: dict[str, Path] = {}

    paths = sorted(
        p
        for p in snapshot_dir.glob("*.txt")
        if p.is_file() and not p.name.startswith(".") and "{" not in p.name and "}" not in p.name
    )

    skip_paths: set[Path] = set()
    for path in paths:
        m = _NUMERIC_DUP_SUFFIX.match(path.name)
        if not m:
            continue
        base = snapshot_dir / f"{m.group(1)}.txt"
        if not base.is_file():
            continue
        try:
            if _file_hash(path) == _file_hash(base):
                plans.append((path, base, "duplicate_same_content_delete_source"))
                skip_paths.add(path)
        except OSError as e:
            errors.append(f"hash failed {path.name}: {e}")

    for path in paths:
        if path in skip_paths:
            continue
        nm = path.name
        if _COPY_SUFFIX.search(nm) and needs_rename_filename(nm):
            errors.append(f"unrecognized copy file: {nm}")
            continue

        if is_canonical_filename(nm):
            used_names[nm] = path
            continue

        if not needs_rename_filename(nm) and " copy" not in nm.lower():
            errors.append(f"skip unknown name: {nm}")
            continue

        ts = resolve_ts(path)
        if ts is None:
            errors.append(f"no ts for {nm}")
            continue

        target_name = format_snapshot_filename(ts)
        target = snapshot_dir / target_name

        if path.resolve() == target.resolve():
            used_names[target_name] = path
            continue

        occupant: Path | None = used_names.get(target_name)
        if occupant is None and target.exists():
            occupant = target

        if occupant is not None and occupant.resolve() != path.resolve():
            try:
                if _file_hash(path) == _file_hash(occupant):
                    plans.append((path, occupant, "duplicate_same_content_delete_source"))
                    used_names.setdefault(target_name, occupant)
                    continue
            except OSError as e:
                errors.append(f"hash failed {nm}: {e}")
                continue

        n = 2
        while (target_name in used_names and used_names[target_name].resolve() != path.resolve()) or (
            target.exists() and target.resolve() != path.resolve()
        ):
            occupant = used_names.get(target_name) if target_name in used_names else target
            try:
                if _file_hash(path) == _file_hash(occupant):
                    plans.append((path, occupant, "duplicate_same_content_delete_source"))
                    used_names.setdefault(target_name, occupant)
                    break
            except OSError as e:
                errors.append(f"hash failed {nm}: {e}")
                break
            target_name = format_snapshot_filename(ts, suffix=str(n))
            target = snapshot_dir / target_name
            n += 1
        else:
            plans.append((path, target, "rename"))
            used_names[target_name] = target

    renamed = removed = 0
    unlink_on_server: list[str] = []

    for src, dst, reason in plans:
        rel_old = _rel_vault(vault, src)
        if reason == "duplicate_same_content_delete_source":
            if verbose or apply:
                print(f"  [{label}] {'✕' if apply else '~'} remove duplicate: {src.name} (= {dst.name})")
            if apply:
                src.unlink()
                unlink_on_server.append(rel_old)
                removed += 1
            else:
                removed += 1
            continue

        if verbose:
            print(f"  [{label}] {'→' if apply else '~'} {src.name}  →  {dst.name}")
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            unlink_on_server.append(rel_old)
            renamed += 1
        else:
            renamed += 1

    return {
        "ok": len(errors) == 0 or renamed + removed > 0,
        "label": label,
        "dir_rel": _rel_vault(vault, snapshot_dir),
        "renamed": renamed,
        "removed": removed,
        "errors": errors,
        "unlink_on_server": sorted(set(unlink_on_server)),
    }


def write_combined_manifest(
    sync_dir: Path,
    *,
    vault: Path,
    results: list[dict[str, Any]],
    apply: bool,
) -> Path:
    sync_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = sync_dir / "action_snapshot_renames.json"
    unlink = sorted({p for r in results for p in r.get("unlink_on_server") or []})
    payload = {
        "version": 2,
        "unlink_on_server": unlink if apply else [],
        "targets": {r["label"]: {k: r[k] for k in ("dir_rel", "renamed", "removed", "errors") if k in r} for r in results},
    }
    if apply:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # (comment)
        legacy_iphone = sync_dir / "iphone_snapshot_renames.json"
        legacy_iphone.write_text(
            json.dumps(
                {
                    "version": 1,
                    "iphone_dir_rel": next((r["dir_rel"] for r in results if r["label"] == "iphone"), ""),
                    "renamed": sum(r.get("renamed", 0) for r in results if r["label"] == "iphone"),
                    "removed_duplicates": sum(r.get("removed", 0) for r in results if r["label"] == "iphone"),
                    "unlink_on_server": unlink,
                    "errors": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return manifest_path
