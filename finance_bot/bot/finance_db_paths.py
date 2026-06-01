"""
Canonical finance.db and read-only vault replica.

Rules:
  • all writes (bot, import, broker) → canonical write DB;
  • vault/.../finance.db — replica for dashboard/Obsidian;
  • replica is updated only via explicit mirror (bot → vault), never rsync vault → bot.

Path overrides — env only (FINANCE_DB_PATH, DATABASE_URL, VAULT_PATH,
FINANCE_USE_VAULT_DB, FINANCE_BOT_ROOT).
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

from .vault_paths import VaultPaths

log = logging.getLogger("finance.db_paths")

_SQLITE_PREFIXES = ("sqlite+aiosqlite:///", "sqlite:///")


def finance_bot_root() -> Path:
    raw = (os.environ.get("FINANCE_BOT_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def sqlite_path_from_database_url(url: str) -> Optional[Path]:
    u = (url or "").strip()
    for prefix in _SQLITE_PREFIXES:
        if u.startswith(prefix):
            raw = u[len(prefix) :]
            if "?" in raw:
                raw = raw.split("?", 1)[0]
            return Path(raw)
    return None


def _vault_root_from_env() -> Optional[Path]:
    for key in ("VAULT_PATH", "OBSIDIAN_VAULT_PATH", "SYNC_SERVER_VAULT_PATH"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return Path(v).expanduser().resolve()
    return None


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_canonical_write_db(
    *,
    finance_db_path: Optional[str] = None,
    database_url: Optional[str] = None,
    bot_root: Optional[Path] = None,
) -> Path:
    """
    Single path for INSERT/UPDATE from bot and import scripts.

    Priority:
      1. FINANCE_DB_PATH / finance_db_path argument
      2. Absolute path from DATABASE_URL
      3. Relative DATABASE_URL → under finance_bot (FINANCE_BOT_ROOT)
      4. FINANCE_USE_VAULT_DB=1 and existing vault replica (legacy opt-in)
      5. {bot_root}/finance.db
    """
    explicit = (finance_db_path or os.environ.get("FINANCE_DB_PATH") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    url = (database_url or os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./finance.db").strip()
    path_part = sqlite_path_from_database_url(url)
    root = bot_root or finance_bot_root()

    if path_part is not None:
        if path_part.is_absolute():
            return path_part.resolve()
        return (root / path_part).resolve()

    if _env_truthy("FINANCE_USE_VAULT_DB"):
        vault = _vault_root_from_env()
        if vault is not None:
            replica = VaultPaths(vault).finance_db()
            if replica.is_file():
                log.warning(
                    "FINANCE_USE_VAULT_DB=1: writing to vault replica %s (legacy). "
                    "Prefer FINANCE_DB_PATH on canonical + mirror.",
                    replica,
                )
                return replica.resolve()

    return (root / "finance.db").resolve()


def resolve_vault_replica_db(vault: Optional[Path] = None) -> Optional[Path]:
    root = vault or _vault_root_from_env()
    if root is None:
        return None
    return VaultPaths(root.expanduser().resolve()).finance_db()


def mirror_canonical_to_vault_replica(
    *,
    canonical: Optional[Path] = None,
    replica: Optional[Path] = None,
) -> bool:
    """Atomically copy canonical → vault replica (temp + replace). Returns True if copied."""
    src = canonical or resolve_canonical_write_db()
    dst = replica or resolve_vault_replica_db()
    if dst is None:
        return False
    if not src.is_file():
        log.warning("mirror: canonical DB not found: %s", src)
        return False
    if src.resolve() == dst.resolve():
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp-sync")
    try:
        try:
            con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.close()
        except sqlite3.Error:
            pass
        shutil.copy2(src, tmp)
        tmp.replace(dst)
        log.info("mirror: %s → %s", src, dst)
        verify_replica_matches_canonical(canonical=src, replica=dst)
        return True
    except OSError as e:
        log.error("mirror failed %s → %s: %s", src, dst, e)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False


def database_url_for_path(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.expanduser().resolve()}"


def _db_transaction_stats(path: Path) -> tuple[Optional[int], int]:
    if not path.is_file():
        return None, 0
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        row = con.execute("SELECT max(id), count(*) FROM transactions").fetchone()
        con.close()
        return (int(row[0]) if row[0] is not None else None, int(row[1] or 0))
    except sqlite3.Error as e:
        log.warning("stats failed for %s: %s", path, e)
        return None, 0


def log_finance_db_layout() -> None:
    canonical = resolve_canonical_write_db()
    replica = resolve_vault_replica_db()
    c_max, c_cnt = _db_transaction_stats(canonical)
    r_max, r_cnt = (None, 0)
    if replica is not None:
        r_max, r_cnt = _db_transaction_stats(replica)
    log.info(
        "finance DB layout: canonical=%s (max_id=%s, n=%s); replica=%s (max_id=%s, n=%s)",
        canonical,
        c_max,
        c_cnt,
        replica,
        r_max,
        r_cnt,
    )
    if replica is not None and canonical.resolve() == replica.resolve():
        log.error(
            "canonical and vault replica point to the same file (%s). "
            "Disable FINANCE_USE_VAULT_DB and set FINANCE_DB_PATH outside vault.",
            canonical,
        )


def bootstrap_canonical_from_replica_if_missing() -> bool:
    """If canonical is missing but replica exists — one-time copy replica → canonical."""
    canonical = resolve_canonical_write_db()
    if canonical.is_file():
        return False
    replica = resolve_vault_replica_db()
    if replica is None or not replica.is_file():
        return False
    if canonical.resolve() == replica.resolve():
        return False
    canonical.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(replica, canonical)
    log.warning(
        "bootstrap: canonical missing, copied from vault replica %s → %s",
        replica,
        canonical,
    )
    return True


def detect_split_brain() -> None:
    """Warn if replica is newer than canonical — no automatic merge."""
    canonical = resolve_canonical_write_db()
    replica = resolve_vault_replica_db()
    if replica is None or not canonical.is_file() or not replica.is_file():
        return
    if canonical.resolve() == replica.resolve():
        return
    c_max, _ = _db_transaction_stats(canonical)
    r_max, _ = _db_transaction_stats(replica)
    if r_max is not None and c_max is not None and r_max > c_max:
        log.error(
            "split-brain: vault replica newer than canonical (replica max_id=%s > canonical max_id=%s). "
            "Not overwriting canonical automatically. Check FINANCE_DB_PATH and merge manually if needed.",
            r_max,
            c_max,
        )


def verify_replica_matches_canonical(
    *,
    canonical: Optional[Path] = None,
    replica: Optional[Path] = None,
) -> bool:
    src = canonical or resolve_canonical_write_db()
    dst = replica or resolve_vault_replica_db()
    if dst is None or not dst.is_file() or not src.is_file():
        return False
    if src.resolve() == dst.resolve():
        return True
    c_max, c_cnt = _db_transaction_stats(src)
    r_max, r_cnt = _db_transaction_stats(dst)
    ok = c_max == r_max and c_cnt == r_cnt
    if not ok:
        log.error(
            "replica drift after mirror: canonical max_id=%s n=%s; replica max_id=%s n=%s",
            c_max,
            c_cnt,
            r_max,
            r_cnt,
        )
    return ok
