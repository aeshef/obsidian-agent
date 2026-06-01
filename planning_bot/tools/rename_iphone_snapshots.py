#!/usr/bin/env python3
"""
Переименование IPhone/*.txt: DD.MM.YYYY, HH:MM.txt → YYYY-MM-DD, HH-MM.txt (сортировка по имени).

  python tools/rename_iphone_snapshots.py              # dry-run
  python tools/rename_iphone_snapshots.py --apply
  python tools/rename_iphone_snapshots.py --apply --vault /path

Пишет манифест .sync/iphone_snapshot_renames.json (unlink_on_server — старые имена для SSH cleanup).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
if str(_PKG.parent) not in sys.path:
    sys.path.insert(0, str(_PKG.parent))

from planning_bot.core.config import IPHONE_CONTEXT_DIR
from planning_bot.services.iphone_context_parser import parse_iphone_file
from planning_bot.services.iphone_snapshot_names import (
    format_snapshot_filename,
    is_canonical_filename,
    is_legacy_filename,
    parse_filename_ts,
)

_COPY_SUFFIX = re.compile(r"\s+copy\.txt$", re.IGNORECASE)


def vault_root_from_iphone_dir(iphone_dir: Path) -> Path:
    """300_Дашборды/Данные/Действия/IPhone → корень vault."""
    return iphone_dir.resolve().parents[3]


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_ts(path: Path) -> datetime | None:
    snap = parse_iphone_file(path)
    if snap and snap.get("ts"):
        try:
            return datetime.fromisoformat(str(snap["ts"]))
        except ValueError:
            pass
    return parse_filename_ts(path.name)


def _rel_vault(vault: Path, path: Path) -> str:
    return str(path.resolve().relative_to(vault.resolve()))


def rename_iphone_snapshots(
    *,
    iphone_dir: Path,
    vault: Path,
    sync_dir: Path,
    apply: bool,
) -> dict:
    iphone_dir = iphone_dir.resolve()
    vault = vault.resolve()
    if not iphone_dir.is_dir():
        return {"ok": True, "renamed": 0, "removed": 0, "skipped": 0, "errors": []}

    plans: list[tuple[Path, Path, str]] = []
    errors: list[str] = []
    used_names: dict[str, Path] = {}

    paths = sorted(p for p in iphone_dir.glob("*.txt") if p.is_file() and not p.name.startswith("."))

    for path in paths:
        nm = path.name
        if _COPY_SUFFIX.search(nm) and not is_legacy_filename(nm) and not is_canonical_filename(nm):
            errors.append(f"unrecognized copy file: {nm}")
            continue

        if is_canonical_filename(nm):
            used_names[nm] = path
            continue

        if not is_legacy_filename(nm) and " copy" not in nm.lower():
            errors.append(f"skip unknown name: {nm}")
            continue

        ts = _resolve_ts(path)
        if ts is None:
            errors.append(f"no ts for {nm}")
            continue

        target_name = format_snapshot_filename(ts)
        n = 2
        while target_name in used_names and used_names[target_name] != path:
            target_name = format_snapshot_filename(ts, suffix=str(n))
            n += 1

        target = iphone_dir / target_name
        if path.resolve() == target.resolve():
            used_names[target_name] = path
            continue

        if target.exists() and target != path:
            try:
                if _file_hash(path) == _file_hash(target):
                    plans.append((path, target, "duplicate_same_content_delete_source"))
                    used_names.setdefault(target_name, target)
                    continue
            except OSError as e:
                errors.append(f"hash failed {nm}: {e}")
                continue
            while target.exists() and target != path:
                target_name = format_snapshot_filename(ts, suffix=str(n))
                target = iphone_dir / target_name
                n += 1

        plans.append((path, target, "rename"))
        used_names[target_name] = target

    renamed = removed = 0
    unlink_on_server: list[str] = []

    for src, dst, reason in plans:
        rel_old = _rel_vault(vault, src)
        if reason == "duplicate_same_content_delete_source":
            print(f"  {'✕' if apply else '~'} remove duplicate: {src.name} (= {dst.name})")
            if apply:
                src.unlink()
                unlink_on_server.append(rel_old)
                removed += 1
            else:
                removed += 1
            continue

        print(f"  {'→' if apply else '~'} {src.name}  →  {dst.name}")
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            unlink_on_server.append(rel_old)
            renamed += 1
        else:
            renamed += 1

    manifest = {
        "version": 1,
        "iphone_dir_rel": _rel_vault(vault, iphone_dir),
        "renamed": renamed,
        "removed_duplicates": removed,
        "unlink_on_server": sorted(set(unlink_on_server)),
        "errors": errors,
    }
    sync_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = sync_dir / "iphone_snapshot_renames.json"
    if apply and (renamed or removed):
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif apply:
        manifest_path.write_text(
            json.dumps({**manifest, "unlink_on_server": []}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(
        f"\nИтого: rename={renamed}, dup_removed={removed}, "
        f"errors={len(errors)}, manifest={'written' if apply else 'dry-run'}"
    )
    return {
        "ok": len(errors) == 0 or renamed + removed > 0,
        "renamed": renamed,
        "removed": removed,
        "errors": errors,
        "manifest_path": str(manifest_path),
        "unlink_on_server": manifest["unlink_on_server"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Rename IPhone snapshot files for lexicographic sort")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--vault", type=str, default="")
    ap.add_argument("--sync-dir", type=str, default="")
    args = ap.parse_args()

    if args.vault:
        os.environ["VAULT_PATH"] = args.vault

    iphone_dir = IPHONE_CONTEXT_DIR.resolve()
    vault = Path(args.vault).expanduser().resolve() if args.vault else vault_root_from_iphone_dir(iphone_dir)
    sync_dir = Path(args.sync_dir or os.environ.get("SYNC_STATE_DIR", "")).expanduser()
    if not sync_dir.is_dir():
        sync_dir = vault / ".sync"

    result = rename_iphone_snapshots(
        iphone_dir=iphone_dir,
        vault=vault,
        sync_dir=sync_dir,
        apply=args.apply,
    )
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
