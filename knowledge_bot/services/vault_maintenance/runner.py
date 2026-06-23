"""Daily vault maintenance orchestration (local config/vault_maintenance.yaml)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from knowledge_bot.core.config import load_config
from knowledge_bot.services.maintenance_metrics import (
    append_daily_record,
    collect_deletions_from_steps,
    collect_vault_snapshot,
    extract_step_metrics,
    refresh_sidecar_from_maintenance_log,
    render_maintenance_charts,
    write_deletion_manifest,
    write_maintenance_run_sidecar,
)
from knowledge_bot.services.tag_cleanup import sanitize_malformed_tags

# retag/refill/reprocess exit 3 when DeepSeek DNS is down (--apply skipped, not a hard failure)
_LLM_NETWORK_SKIP_EXIT = 3


def _step_failed(returncode: int) -> bool:
    return returncode not in (0, _LLM_NETWORK_SKIP_EXIT)


def _kb_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _load_dotenv() -> None:
    for p in (_kb_root() / ".env", _kb_root().parent / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        break


def load_maintenance_config(agent_config_path: Path) -> dict[str, Any]:
    """Load local maintenance config; fallback example is intentionally safe/dry-run."""
    candidates = [
        agent_config_path / "vault_maintenance.yaml",
        _kb_root() / "config" / "vault_maintenance.yaml",
        _kb_root() / "config" / "vault_maintenance.yaml.example",
    ]
    for p in candidates:
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
    return {"daily": {"enabled": False}}


def _resolve_sync_dir(vault: Path, sync_dir: Path | None) -> Path:
    if sync_dir is not None and str(sync_dir).strip():
        return sync_dir
    envp = (os.environ.get("SYNC_STATE_DIR") or os.environ.get("OBSIDIAN_SYNC_DIR") or "").strip()
    if envp:
        return Path(envp)
    return vault / ".sync"


def _marker_path(sync_dir: Path, basename: str) -> Path:
    return sync_dir / basename


def _write_marker(sync_dir: Path, marker_basename: str) -> None:
    sync_dir.mkdir(parents=True, exist_ok=True)
    _marker_path(sync_dir, marker_basename).write_text(
        date.today().isoformat() + "\n", encoding="utf-8"
    )


def _should_run_today(
    sync_dir: Path, marker_basename: str, force: bool, env_force: bool
) -> bool:
    if force or env_force:
        return True
    m = _marker_path(sync_dir, marker_basename)
    if not m.exists():
        return True
    try:
        return m.read_text(encoding="utf-8").strip() != date.today().isoformat()
    except OSError:
        return True


def run_daily_maintenance(
    *,
    sync_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    _load_dotenv()
    cfg = load_config()
    vault = cfg.vault_path
    sdir = _resolve_sync_dir(vault, sync_dir)
    mcfg = load_maintenance_config(cfg.agent_config_path)
    daily = mcfg.get("daily") or {}
    marker = str(daily.get("marker_basename", "daily_vault_write_maintenance_date.txt"))
    env_force = os.environ.get("FORCE_VAULT_MAINTENANCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    f = force or env_force

    if not daily.get("enabled", True) and not f:
        _write_marker(sdir, marker)
        return {
            "skipped": True,
            "reason": "vault_maintenance.daily.enabled=false",
            "wrote_marker": True,
        }

    if not _should_run_today(sdir, marker, bool(force), bool(env_force)):
        try:
            refresh_sidecar_from_maintenance_log(vault, sdir)
        except OSError:
            pass
        return {
            "skipped": True,
            "reason": "already_ran_today",
            "sync_dir": str(sdir),
        }

    kb = _kb_root()
    py = sys.executable
    env = os.environ.copy()
    env["VAULT_PATH"] = str(vault)
    env["PYTHONPATH"] = str(kb.parent) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    ts_start = datetime.now().isoformat(timespec="seconds")
    before = collect_vault_snapshot(vault)
    out: dict[str, Any] = {
        "sync_dir": str(sdir),
        "steps": [],
        "ok": True,
        "ts_start": ts_start,
    }

    def _run(name: str, args: list[str]) -> int:
        cmd = " ".join(args)
        print(f"[vault_daily_maintenance] START {name} ({cmd})", flush=True)
        t0 = time.monotonic()
        r = subprocess.run(
            [py, *args],
            cwd=str(kb),
            env=env,
            text=True,
            capture_output=True,
        )
        secs = round(time.monotonic() - t0, 1)
        rc = int(r.returncode or 0)
        metrics = extract_step_metrics(name, r.stdout or "", r.stderr or "")
        out["steps"].append(
            {
                "name": name,
                "returncode": rc,
                "seconds": secs,
                "stdout_tail": (r.stdout or "")[-4000:],
                "stderr_tail": (r.stderr or "")[-2000:],
                "metrics": metrics,
            }
        )
        print(
            f"[vault_daily_maintenance] DONE  {name} code={rc} in {secs}s",
            flush=True,
        )
        return rc

    hcfg = mcfg.get("sync_hubs") or {}
    if hcfg.get("enabled", True):
        args = ["tools/sync_hubs.py", "--vault", str(vault)]
        if hcfg.get("write", False):
            args.append("--apply")
        if _step_failed(_run("sync_hubs", args)):
            out["ok"] = False

    wcfg = mcfg.get("apply_wikilinks") or {}
    if wcfg.get("enabled", True):
        wargs = [
            "tools/apply_wikilinks_batch.py",
            "--vault",
            str(vault),
            "--limit",
            str(int(wcfg.get("limit", 30))),
        ]
        if wcfg.get("apply", False):
            wargs.append("--apply")
        if _step_failed(_run("apply_wikilinks_batch", wargs)):
            out["ok"] = False

    fcfg = mcfg.get("refill_singleton_tags") or {}
    if fcfg.get("enabled", True):
        fargs = [
            "tools/refill_singleton_tags.py",
            "--vault",
            str(vault),
            "--limit",
            str(int(fcfg.get("limit", 30))),
            "--topic-max-count",
            str(int(fcfg.get("topic_max_count", 2))),
        ]
        if fcfg.get("apply", False):
            fargs.append("--apply")
        if _step_failed(_run("refill_singleton_tags", fargs)):
            out["ok"] = False

    utcfg = mcfg.get("retag_untagged") or {}
    if utcfg.get("enabled", True):
        utargs = [
            "tools/retag_notes.py",
            "--vault",
            str(vault),
            "--no-tags",
            "--limit",
            str(int(utcfg.get("limit", 40))),
        ]
        if utcfg.get("apply", False):
            utargs.append("--apply")
        if _step_failed(_run("retag_untagged", utargs)):
            out["ok"] = False

    rtcfg = mcfg.get("retag_notes") or {}
    if rtcfg.get("enabled", True):
        rtargs = [
            "tools/retag_notes.py",
            "--vault",
            str(vault),
            "--limit",
            str(int(rtcfg.get("limit", 35))),
            "--threshold",
            str(int(rtcfg.get("threshold", 1))),
        ]
        if rtcfg.get("apply", False):
            rtargs.append("--apply")
        if rtcfg.get("strip_obsolete_singleton_topics", True):
            rtargs.append("--strip-singleton-topics")
        if _step_failed(_run("retag_notes", rtargs)):
            out["ok"] = False

    rcfg = mcfg.get("reprocess_notes") or {}
    if rcfg.get("enabled", True):
        rargs = [
            "tools/reprocess_notes.py",
            "--vault",
            str(vault),
            "--limit",
            str(int(rcfg.get("limit", 8))),
        ]
        if rcfg.get("apply", False):
            rargs.append("--apply")
        if _step_failed(_run("reprocess_notes", rargs)):
            out["ok"] = False

    tcfg = mcfg.get("sanitize_malformed_tags") or {}
    if tcfg.get("enabled", True):
        t0 = time.monotonic()
        tag_cleanup_rows = sanitize_malformed_tags(
            vault, cfg.agent_config_path, apply=bool(tcfg.get("apply", False))
        )
        tag_cleanup_stdout = "\n".join(
            f"{rel}: removed={removed} tags={tags}"
            for rel, removed, tags in tag_cleanup_rows[:30]
        )
        if len(tag_cleanup_rows) > 30:
            tag_cleanup_stdout += f"\n... {len(tag_cleanup_rows) - 30} more"
        if not tag_cleanup_stdout:
            tag_cleanup_stdout = "Malformed tags: 0"
        out["steps"].append(
            {
                "name": "sanitize_malformed_tags",
                "returncode": 0,
                "seconds": round(time.monotonic() - t0, 1),
                "stdout_tail": tag_cleanup_stdout[-4000:],
                "stderr_tail": "",
                "metrics": {"malformed_tags_cleaned_notes": len(tag_cleanup_rows)},
            }
        )

    ecfg = mcfg.get("export_orphans") or {}
    if ecfg.get("enabled", True):
        eargs = [
            "tools/export_orphans_maintenance.py",
            "--vault",
            str(vault),
            "--print-limit",
            str(int(ecfg.get("print_limit", 100))),
        ]
        if ecfg.get("apply", False):
            eargs.append("--apply")
        rehydrate_limit = int(ecfg.get("rehydrate_limit", 0) or 0)
        if rehydrate_limit > 0:
            eargs.extend(
                [
                    "--rehydrate-limit",
                    str(rehydrate_limit),
                    "--rehydrate-max-mb",
                    str(int(ecfg.get("rehydrate_max_mb", 25))),
                ]
            )
        if (ecfg.get("cleanup") or {}).get("enabled", False):
            eargs.append("--allow-delete")
            eargs.extend(
                [
                    "--delete-cap",
                    str(int((ecfg.get("cleanup") or {}).get("delete_cap", 0))),
                ]
            )
        if bool((ecfg.get("cleanup") or {}).get("fix_broken_refs", False)):
            eargs.append("--cleanup-broken-refs")
        if bool((ecfg.get("cleanup") or {}).get("fix_broken_body_refs", False)):
            eargs.append("--cleanup-broken-body-refs")
        if _step_failed(_run("export_orphans", eargs)):
            out["ok"] = False

    dcfg = mcfg.get("apply_duplicates") or {}
    if dcfg.get("enabled", True):
        cap = int(dcfg.get("max_delete_per_run", 100))
        dry_args = ["tools/apply_duplicates_resolution.py"]
        if _step_failed(_run("apply_duplicates_dryrun", dry_args)):
            out["ok"] = False
        else:
            last = out["steps"][-1] if out["steps"] else {}
            metrics = last.get("metrics") or {}
            n_del = int(metrics.get("duplicates_deleted_lines", 0) or 0)
            print(
                f"[vault_daily_maintenance] apply_duplicates: dry-run found {n_del} deletions (cap={cap})",
                flush=True,
            )
            if n_del > 0:
                if n_del > cap:
                    print(
                        f"[vault_daily_maintenance] apply_duplicates: over cap ({n_del}>{cap}), skip apply",
                        flush=True,
                    )
                    out["ok"] = False
                else:
                    if dcfg.get("apply", False):
                        apply_args = ["tools/apply_duplicates_resolution.py", "--apply"]
                        if _step_failed(_run("apply_duplicates", apply_args)):
                            out["ok"] = False
            else:
                print(
                    "[vault_daily_maintenance] apply_duplicates: nothing to delete",
                    flush=True,
                )

    scfg = mcfg.get("singleton_tags_report") or {}
    if scfg.get("enabled", False):
        sargs = ["tools/strip_singleton_tags.py", "--vault", str(vault)]
        if scfg.get("apply", False):
            sargs.append("--apply")
        if _step_failed(_run("singleton_tags_report", sargs)):
            out["ok"] = False

    ts_end = datetime.now().isoformat(timespec="seconds")
    out["ts_end"] = ts_end
    after = collect_vault_snapshot(vault)
    out["before"] = before
    out["after"] = after
    deletions = collect_deletions_from_steps(out["steps"])
    try:
        write_deletion_manifest(sdir, deletions, ts_end)
        write_maintenance_run_sidecar(sdir, out)
    except OSError as e:
        out["manifest_error"] = str(e)
    try:
        append_daily_record(
            vault,
            before=before,
            after=after,
            steps=out["steps"],
            ok=bool(out.get("ok")),
            ts_start=ts_start,
            ts_end=ts_end,
        )
        render_maintenance_charts(vault)
    except Exception as e:
        out["history_error"] = str(e)

    if out.get("ok"):
        try:
            _write_marker(sdir, marker)
        except OSError as e:
            out["marker_error"] = str(e)
            out["ok"] = False
    return out
