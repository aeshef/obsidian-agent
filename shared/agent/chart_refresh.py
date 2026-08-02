"""Allowlisted on-demand chart builder runners (paths/timeouts from platform config)."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("shared.agent.chart_refresh")


def _bots_root() -> Path:
    raw = (os.environ.get("AGENT_ROOT") or "").strip()
    return Path(raw).resolve() if raw else Path.cwd().resolve()


def _refresh_cfg() -> dict[str, Any]:
    from shared.agent.platform_config import load_platform_config

    block = load_platform_config().get("chart_refresh") or {}
    return block if isinstance(block, dict) else {}


def refresh_enabled() -> bool:
    cfg = _refresh_cfg()
    if "enabled" in cfg:
        try:
            return bool(int(cfg.get("enabled") or 0))
        except (TypeError, ValueError):
            return str(cfg.get("enabled")).strip().lower() in ("1", "true", "yes", "on")
    return False


def list_builder_keys() -> list[str]:
    builders = _refresh_cfg().get("builders") or {}
    if not isinstance(builders, dict):
        return []
    return sorted(str(k) for k in builders.keys())


def _resolve_script(rel: str) -> Path | None:
    root = _bots_root()
    rel_n = str(rel or "").strip().lstrip("/")
    if not rel_n or ".." in Path(rel_n).parts:
        return None
    path = (root / rel_n).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path


def _builder_entry(key: str) -> dict[str, Any] | None:
    builders = _refresh_cfg().get("builders") or {}
    if not isinstance(builders, dict):
        return None
    raw = builders.get(key)
    if isinstance(raw, str):
        return {"script": raw, "args": ["--vault", "{vault}"]}
    if isinstance(raw, dict) and raw.get("script"):
        return raw
    return None


def match_builder_keys(*, builder: str = "", family: str = "") -> list[str]:
    keys = list_builder_keys()
    b = (builder or "").strip().lower()
    f = (family or "").strip().lower()
    if b:
        if b in keys:
            return [b]
        return [k for k in keys if b in k]
    if f:
        return [k for k in keys if f in k or k.startswith(f)]
    return []


def run_chart_builder(key: str, *, vault: Path | None) -> tuple[bool, str]:
    """Run one allowlisted builder. Returns (ok, short status without vault secrets)."""
    entry = _builder_entry(key)
    if not entry:
        return False, f"unknown_builder:{key}"
    script = _resolve_script(str(entry.get("script") or ""))
    if script is None:
        return False, f"script_missing:{key}"

    from shared.agent.platform_config import platform_int

    timeout = max(15, platform_int("chart_refresh", "timeout_sec", default=180))
    args_tmpl = entry.get("args")
    if not isinstance(args_tmpl, list) or not args_tmpl:
        args_tmpl = ["--vault", "{vault}"]
    vault_s = str(vault.resolve()) if vault is not None else ""
    argv = [sys.executable, str(script)]
    for a in args_tmpl:
        argv.append(str(a).replace("{vault}", vault_s))

    env = os.environ.copy()
    root = str(_bots_root())
    env["AGENT_ROOT"] = root
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout:{key}:{timeout}s"
    except OSError as e:
        log.warning("chart refresh spawn failed key=%s: %s", key, e)
        return False, f"spawn_error:{key}"

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = err[-1][:160] if err else "exit_%s" % proc.returncode
        log.warning("chart refresh failed key=%s code=%s", key, proc.returncode)
        return False, f"failed:{key}:{tail}"
    return True, f"ok:{key}"
