#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import urllib.request
import httpx
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.vault_paths import VaultPaths, vault_root_optional  # noqa: E402
from bot.services.ssl_ca import httpx_client_kwargs  # noqa: E402


def _httpx_client(*, http2: bool = False, timeout: float = 25.0) -> httpx.Client:
    kw = httpx_client_kwargs(timeout=timeout)
    if http2:
        kw["http2"] = True
    return httpx.Client(**kw)


def dbg(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    try:
        vault = vault_root_optional()
        if vault:
            lf = VaultPaths(vault).portfolio_log_file()
            lf.parent.mkdir(parents=True, exist_ok=True)
            with lf.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass
    print(f"[tinkoff_sync] {msg}", file=sys.stderr, flush=True)


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _id_tail(ref: str) -> str:
    s = str(ref)
    return f"…{s[-4:]}" if len(s) > 4 else "****"


_INT_ACCOUNT_TYPE = {
    0: "ACCOUNT_TYPE_UNSPECIFIED",
    1: "ACCOUNT_TYPE_TINKOFF",
    2: "ACCOUNT_TYPE_TINKOFF_IIS",
    3: "ACCOUNT_TYPE_INVEST_BOX",
    4: "ACCOUNT_TYPE_INVEST_FUND",
}


def _norm_account_type_field(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw if raw.startswith("ACCOUNT_TYPE_") else None
    if isinstance(raw, int):
        return _INT_ACCOUNT_TYPE.get(raw, f"ACCOUNT_TYPE_UNKNOWN_{raw}")
    return None


def fetch_tinkoff_summary(token: str) -> dict:
    # Use user's integration TinkoffClient API
    total_rub = 0.0
    day_change_rub = 0.0  # optional, keep 0 for now
    by_sector = {}
    dbginfo: Dict[str, Any] = {
        "imported_client": False,
        "accounts_v2": [],
        "main_account": None,
        "accounts_rest": [],
        "account_types": {},
        "equities": {},
        "positions_counts": {},
        "sectors": [],
        "errors": [],
    }

    try:
        vault = vault_root_optional()
        if vault:
            sys.path.append(str(VaultPaths(vault).tg_alerting_import_root()))
        from tg_alerting.integrations.tinkoff import TinkoffClient
        dbg("Imported TinkoffClient from tg_alerting.integrations.tinkoff")
        dbginfo["imported_client"] = True
    except ModuleNotFoundError:
        # Optional legacy package — Invest SDK / REST path below is the normal install.
        TinkoffClient = None
        dbginfo["imported_client"] = False
    except Exception as e:
        dbg(f"Import TinkoffClient failed: {e}")
        dbginfo["errors"].append(f"import_error: {e}")
        TinkoffClient = None

    if TinkoffClient is not None:
        try:
            dbg("Initializing TinkoffClient (with SDK in venv if available)...")
            vault = vault_root_optional()
            if vault:
                env_bin = VaultPaths(vault).optional_python_env_bin()
                if env_bin is not None:
                    os.environ.setdefault("PATH", f"{env_bin}:{os.environ.get('PATH','')}")
            api = TinkoffClient(token)
            accounts = api.get_accounts_v2() or []
            dbg(f"Accounts v2: count={len(accounts)}")
            dbginfo["accounts_v2"] = accounts
            if not accounts:
                main = api.get_main_account_id()
                dbg(f"Main account fallback: {_id_tail(str(main)) if main else 'none'}")
                accounts = [main] if main else []
                dbginfo["main_account"] = main

            all_positions = []
            for acc_id in accounts:
                dbg(f"Fetching equity for account {_id_tail(str(acc_id))}")
                try:
                    eq = api.get_total_equity_rub(acc_id)
                    dbg(f"Equity {_id_tail(str(acc_id))}: ok" if eq is not None else f"Equity {_id_tail(str(acc_id))}: empty")
                    if eq is not None:
                        total_rub += float(eq)
                        dbginfo["equities"][acc_id] = float(eq)
                    pos = api.get_positions_detailed(acc_id) or []
                    dbg(f"Positions {_id_tail(str(acc_id))}: {len(pos)} items")
                    all_positions.extend(pos)
                    dbginfo["positions_counts"][acc_id] = len(pos)
                except Exception as e:
                    dbg(f"Error account {_id_tail(str(acc_id))}: {e}")
                    dbginfo["errors"].append(f"account_error {_id_tail(str(acc_id))}: {e}")
                    continue
            if all_positions:
                by_sector = api.aggregate_by_sector(all_positions)
                dbg(f"Sectors: {list(by_sector.keys())}")
                dbginfo["sectors"] = list(by_sector.keys())
            if total_rub == 0 and not accounts:
                dbg("No accounts fetched; check token or API availability")
                dbginfo["errors"].append("no_accounts")
        except Exception as e:
            dbg(f"Fatal error in client flow: {e}")
            dbginfo["errors"].append(f"fatal_client: {e}")

    # REST v2 fallback if still empty
    if total_rub == 0:
        try:
            dbg("Trying REST v2 (HTTP/2) UsersService/GetAccounts...")
            base = "https://invest-public-api.tinkoff.ru/rest"
            url_acc = base + "/tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts"
            # prefer HTTP/2; fallback to HTTP/1.1 if not available
            try:
                client_ctx = _httpx_client(http2=True, timeout=25.0)
            except Exception as e:
                dbg(f"HTTP/2 unavailable ({e}); falling back to HTTP/1.1")
                client_ctx = _httpx_client(timeout=25.0)
            # fetch accounts
            with client_ctx as client:
                r = client.post(url_acc, json={}, headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-app-name": "finance-bot/0.1",
                    "User-Agent": "finance-bot/0.1",
                })
                if r.status_code != 200:
                    dbg(f"REST v2 accounts http {r.status_code}: {r.text[:200]}")
                    raise RuntimeError(f"REST v2 accounts http {r.status_code}")
                acc_data = r.json()
            raw_accs = acc_data.get("accounts") or acc_data.get("payload", {}).get("accounts") or []
            accounts: List[str] = []
            atypes: Dict[str, str] = {}
            for a in raw_accs:
                aid = str(a.get("id") or a.get("brokerAccountId") or "")
                if not aid:
                    continue
                accounts.append(aid)
                tnorm = _norm_account_type_field(a.get("type"))
                if tnorm:
                    atypes[aid] = tnorm
            dbginfo["account_types"].update(atypes)
            dbg(f"REST accounts: count={len(accounts)}")
            dbginfo["accounts_rest"] = accounts
            for acc_id in accounts:
                url_port = base + "/tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio"
                # Payload: account_id as string, currency RUB
                payload = {"account_id": str(acc_id)}
                # use separate client context to avoid closed-client issues
                try:
                    c2 = _httpx_client(http2=True, timeout=25.0)
                except Exception:
                    c2 = _httpx_client(timeout=25.0)
                with c2 as client2:
                    r2 = client2.post(url_port, json=payload, headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "x-app-name": "finance-bot/0.1",
                        "User-Agent": "finance-bot/0.1",
                    })
                if r2.status_code != 200:
                    dbg(f"REST v2 portfolio {_id_tail(acc_id)} http {r2.status_code}: {r2.text[:200]}")
                    # 404 — account may have no portfolio, skip
                    if r2.status_code == 404:
                        dbg(f"Account {_id_tail(acc_id)} has no portfolio (404) - skipping")
                    continue
                port = r2.json()
                mv = port.get("totalAmountPortfolio") or port.get("payload", {}).get("totalAmountPortfolio")
                if isinstance(mv, dict) and (mv.get("currency", "").lower() in ("rub", "rur")):
                    units = float(mv.get("units") or 0)
                    nano = float(mv.get("nano") or 0)
                    val = units + nano / 1_000_000_000
                    dbg(f"REST equity {_id_tail(acc_id)}: ok")
                    total_rub += val
                    dbginfo["equities"][acc_id] = val
        except Exception as e:
            dbg(f"REST fallback error: {e}")
            dbginfo["errors"].append(f"rest_error: {e}")

    # Legacy OpenAPI fallback
    if total_rub == 0:
        try:
            dbg("Trying legacy OpenAPI /user/accounts and /portfolio ...")
            base = "https://api-invest.tinkoff.ru/openapi"
            # accounts
            try:
                client2_ctx = _httpx_client(http2=True, timeout=20.0)
            except Exception as e:
                dbg(f"HTTP/2 unavailable for legacy ({e}); falling back to HTTP/1.1")
                client2_ctx = _httpx_client(timeout=20.0)
            with client2_ctx as client2:
                r = client2.get(base + "/user/accounts", headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "x-app-name": "finance-bot/0.1",
                    "User-Agent": "finance-bot/0.1",
                })
                if r.status_code != 200:
                    dbg(f"Legacy accounts http {r.status_code}: {r.text[:200]}")
                    raise RuntimeError(f"legacy http {r.status_code}")
                accs_data = r.json()
                accounts = [
                    str(a.get("brokerAccountId"))
                    for a in accs_data.get("payload", {}).get("accounts", [])
                    if a.get("brokerAccountId")
                ]
                dbg(f"Legacy accounts: count={len(accounts)}")
                dbginfo["accounts_rest"] = dbginfo.get("accounts_rest", []) or accounts
                for acc_id in accounts:
                    url = base + "/portfolio?brokerAccountId=" + acc_id
                    r2 = client2.get(url, headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "x-app-name": "finance-bot/0.1",
                        "User-Agent": "finance-bot/0.1",
                    })
                    if r2.status_code != 200:
                        dbg(f"Legacy portfolio {_id_tail(str(acc_id))} http {r2.status_code}: {r2.text[:200]}")
                        continue
                    port = r2.json()
                    payload = port.get("payload", {})
                    tot = payload.get("totalAmountPortfolio") or payload.get("totalAmountCurrencies")
                    val = None
                    if isinstance(tot, dict):
                        val = float(tot.get("value") or 0.0)
                    dbg(f"Legacy equity {_id_tail(str(acc_id))}: ok")
                    if val:
                        total_rub += float(val)
                        dbginfo["equities"][acc_id] = float(val)
        except Exception as e:
            dbg(f"Legacy fallback error: {e}")
            dbginfo["errors"].append(f"legacy_error: {e}")

    sector_rows = sorted(by_sector.items(), key=lambda x: -x[1]) if by_sector else []
    sector_md = None
    if sector_rows:
        sector_table = ["| Sector | Value RUB |", "|---|---:|"]
        for name, val in sector_rows:
            sector_table.append(f"| {name} | {int(round(val)):,} |".replace(",", " "))
        sector_md = "\n".join(sector_table)

    return {
        "total_rub": round(float(total_rub), 2),
        "day_change_rub": round(float(day_change_rub), 2),
        "sector_table": sector_md,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "_debug": dbginfo,
    }


def write_cache_note(data: dict) -> None:
    vault = vault_root_optional()
    if vault is None:
        return
    cache_note = VaultPaths(vault).portfolio_cache_note()
    cache_note.parent.mkdir(parents=True, exist_ok=True)
    # Put key values into frontmatter so Dataview can read p.total_rub, p.day_change_rub, p.updated_at
    sector_md = data.get("sector_table")
    fm_lines = [
        "---",
        "tags: [investments, portfolio, cache]",
        f"total_rub: {data.get('total_rub', 0)}",
        f"day_change_rub: {data.get('day_change_rub', 0)}",
        f"updated_at: '{data.get('updated_at','')}'",
    ]
    if sector_md:
        # store as literal block in frontmatter for easy dv.page access
        fm_lines.append("sector_table: |-")
        for line in sector_md.splitlines():
            fm_lines.append(f"  {line}")
    fm_lines.append("---\n")
    body = ""
    cache_note.write_text("\n".join(fm_lines) + body, encoding="utf-8")


def cleanup_temp_notes(max_age_seconds: int = 600) -> Dict[str, Any]:
    """Delete recent empty Untitled*.md files in archive trash from template runs."""
    removed = []
    errors = []
    vault = vault_root_optional()
    if vault is None:
        return {"removed": removed, "errors": errors}
    trash_dir = VaultPaths(vault).trash_dir()
    now = time.time()
    try:
        if trash_dir.exists():
            for p in trash_dir.iterdir():
                try:
                    if not p.is_file():
                        continue
                    name = p.name
                    if not (name.startswith("Untitled") and name.endswith(".md")):
                        continue
                    stat = p.stat()
                    size_ok = stat.st_size <= 10
                    age_ok = (now - stat.st_mtime) <= max_age_seconds
                    if size_ok and age_ok:
                        p.unlink()
                        removed.append(name)
                except Exception as e:
                    errors.append(f"{p.name}: {e}")
    except Exception as e:
        errors.append(str(e))
    return {"removed": removed, "errors": errors}


def main() -> None:
    merged: Dict[str, str] = {}
    vault = vault_root_optional()
    if vault:
        merged.update(load_env(VaultPaths(vault).legacy_automation_env()))
    merged.update(load_env(PROJECT_ROOT / ".env"))
    token = merged.get("TINKOFF_API_TOKEN", "").strip()
    summary = fetch_tinkoff_summary(token) if token else {
        "total_rub": 0,
        "day_change_rub": 0,
        "sector_table": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_cache_note(summary)
    cleanup = cleanup_temp_notes()
    tg_exists = False
    log_file = ""
    if vault:
        vp = VaultPaths(vault)
        tg_exists = (vp.tg_alerting_import_root() / "tg_alerting" / "integrations" / "tinkoff.py").exists()
        log_file = str(vp.portfolio_log_file())
    print(json.dumps({
        "ok": True,
        "debug": {
            "import_client": tg_exists,
            "log_file": log_file,
            **summary.get("_debug", {}),
            "cleanup": cleanup,
        },
        **summary
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()


