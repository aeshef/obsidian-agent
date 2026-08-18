#!/usr/bin/env python3
"""Print vault-relative paths from last_maintenance_deleted_paths.json (one per line).

Stdlib only: obsidian_sync.sh calls this from system python3 and from the knowledge venv.
Accepts both path-dict entries and bare strings in `deleted`.
"""
from __future__ import annotations

import json
import pathlib
import sys


def iter_manifest_relpaths(data: object) -> list[str]:
    if not isinstance(data, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data.get("deleted") or []:
        raw = item.get("path") if isinstance(item, dict) else item
        path = str(raw or "").strip()
        if not path or path in seen:
            continue
        if ".." in pathlib.Path(path).parts:
            continue
        seen.add(path)
        out.append(path)
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: print_deleted_manifest.py MANIFEST VAULT", file=sys.stderr)
        return 2
    manifest_path, vault_str = args
    vault = pathlib.Path(vault_str).resolve()
    try:
        payload = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    for rel in iter_manifest_relpaths(payload):
        try:
            resolved = (vault / rel).resolve()
            resolved.relative_to(vault)
        except (ValueError, OSError):
            continue
        print(rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
