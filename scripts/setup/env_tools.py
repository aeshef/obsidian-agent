"""Atomic .env helpers for guided onboarding (append-only hints, set secrets)."""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterable

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.setup.env_patch import collect_env_hints, patch_env_file

_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def repo_root() -> Path:
    return _ROOT


def env_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".env"


def parse_env_keys(path: Path) -> dict[str, str]:
    """Return key -> raw value (may be empty)."""
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _KEY_RE.match(line)
        if not m:
            continue
        key = m.group(1)
        _, _, val = line.partition("=")
        out[key] = val.strip().strip('"').strip("'")
    return out


def append_hints(
    path: Path,
    *,
    modules: dict[str, bool],
    connectors: dict[str, bool],
    dry_run: bool = False,
) -> list[str]:
    hints = collect_env_hints(connectors, modules=modules, include_core=True)
    return patch_env_file(path, hints, dry_run=dry_run)


def set_env_value(
    path: Path,
    key: str,
    value: str,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> str:
    """
    Set one key in .env. Never overwrites non-empty values unless force=True.
    Returns: created | updated | skipped | dry-run
    """
    key = key.strip()
    if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        raise ValueError(f"invalid env key: {key!r}")
    val = value.strip()
    if not val:
        raise ValueError("refuse to set empty value (use append-hints for placeholders)")

    path = Path(path)
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()

    existing: dict[str, int] = {}
    for i, line in enumerate(lines):
        m = _KEY_RE.match(line)
        if m:
            existing[m.group(1)] = i

    if val.startswith('"') and val.endswith('"'):
        new_line = f"{key}={val}"
    elif re.search(r"[\s#'\"\\$`]", val):
        esc = val.replace("\\", "\\\\").replace('"', '\\"')
        new_line = f'{key}="{esc}"'
    else:
        new_line = f"{key}={val}"

    if key in existing:
        idx = existing[key]
        old = lines[idx]
        _, _, old_val = old.partition("=")
        if old_val.strip().strip('"').strip("'") and not force:
            return "skipped"
        if dry_run:
            return "dry-run"
        lines[idx] = new_line
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return "updated"

    if dry_run:
        return "dry-run"
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(new_line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "created"


def list_missing(path: Path, keys: Iterable[str]) -> list[str]:
    have = parse_env_keys(path)
    return [k for k in keys if not (have.get(k) or "").strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Idempotent .env onboarding helpers")
    parser.add_argument("--env", default="", help="Path to .env (default: repo/.env)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_patch = sub.add_parser("append-hints", help="Append missing keys from capabilities profile")
    p_patch.add_argument("--dry-run", action="store_true")

    p_set = sub.add_parser("set", help="Set one secret (never overwrites non-empty without --force)")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.add_argument("--force", action="store_true")
    p_set.add_argument("--dry-run", action="store_true")

    p_list = sub.add_parser("list-missing", help="List keys with empty/missing values")
    p_list.add_argument("keys", nargs="+")

    p_status = sub.add_parser("status", help="Show core + enabled connector env keys")

    p_locale = sub.add_parser("set-locale", help="Set AGENT_LOCALE=en|ru and materialize locale YAML")
    p_locale.add_argument("locale", choices=("en", "ru"))
    p_locale.add_argument("--force", action="store_true", help="Overwrite AGENT_LOCALE even if set")
    p_locale.add_argument("--dry-run", action="store_true")
    p_locale.add_argument(
        "--refresh-vault-paths",
        action="store_true",
        help="Replace vault_paths.yaml from locale example (onboarding)",
    )

    args = parser.parse_args(argv)
    root = repo_root()
    ep = Path(args.env) if args.env else env_path(root)

    if args.cmd == "append-hints":
        from shared.capabilities.profile import clear_capabilities_cache, get_capabilities

        clear_capabilities_cache()
        prof = get_capabilities()
        added = append_hints(
            ep,
            modules=dict(prof.modules),
            connectors=dict(prof.connectors),
            dry_run=args.dry_run,
        )
        for line in added:
            print(f"+ {line}")
        print(f"append-hints: {len(added)} line(s) {'(dry-run)' if args.dry_run else 'written'}")
        return 0

    if args.cmd == "set":
        status = set_env_value(ep, args.key, args.value, force=args.force, dry_run=args.dry_run)
        print(f"set {args.key}: {status}")
        return 0

    if args.cmd == "list-missing":
        for k in list_missing(ep, args.keys):
            print(k)
        return 0

    if args.cmd == "set-locale":
        import importlib.util

        dry = bool(getattr(args, "dry_run", False))
        status = set_env_value(ep, "AGENT_LOCALE", args.locale, force=args.force, dry_run=dry)
        print(f"AGENT_LOCALE: {status}")
        if not dry:
            os.environ["AGENT_LOCALE"] = args.locale
            mat_path = root / "scripts/setup/materialize_locale.py"
            spec = importlib.util.spec_from_file_location("materialize_locale", mat_path)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader
            spec.loader.exec_module(mod)
            mod.materialize(args.locale, refresh_vault_paths=args.refresh_vault_paths)
            from shared.domain_messages import clear_domain_messages_cache
            from shared.i18n import clear_messages_cache

            clear_messages_cache()
            clear_domain_messages_cache()
        return 0

    if args.cmd == "status":
        from shared.capabilities.onboarding_catalog import PLAYBOOKS
        from shared.capabilities.profile import clear_capabilities_cache, get_capabilities

        clear_capabilities_cache()
        prof = get_capabilities()
        have = parse_env_keys(ep)
        core = ("VAULT_PATH", "TELEGRAM_UNIFIED_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "DEEPSEEK_API_KEY")
        print("=== core ===")
        for k in core:
            v = have.get(k, "")
            print(f"{k}: {'set' if v.strip() else 'MISSING'}")
        print("=== enabled connectors ===")
        for pb in PLAYBOOKS:
            if not prof.module(pb.module) or not prof.connector(pb.id):
                continue
            for k in pb.env_keys:
                v = have.get(k, "")
                print(f"{pb.id}.{k}: {'set' if v.strip() else 'empty'}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
