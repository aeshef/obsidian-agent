#!/usr/bin/env python3
"""Keep kanban sync from treating monthly archive as data loss.

Protect/force-push still keep genuine local creates and small intentional
deletes. IDs that already live in the closed-tasks archive are not "server
lost" — they must not block a pull of the thinned board, and they must not
be force-pushed back onto it.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ID_RE = re.compile(r"🆔\s*ID:\s*([0-9a-fA-F-]{6,})", re.IGNORECASE)
TASK_START_RE = re.compile(r"^\s*- \[[ xX]\]")
ARCHIVE_HEADING_RE = re.compile(r"^## .+ · \d{4}-\d{2}\s*$", re.MULTILINE)
KANBAN_PLUGIN_RE = re.compile(r"kanban-plugin", re.IGNORECASE)
INTENTIONAL_DELETE_MAX = 5


def ids_of(text: str) -> set[str]:
    return {m.group(1).lower() for m in ID_RE.finditer(text or "")}


def looks_like_archive(text: str) -> bool:
    return bool(ARCHIVE_HEADING_RE.search(text or ""))


def looks_like_board(text: str) -> bool:
    if looks_like_archive(text or ""):
        return False
    return bool(KANBAN_PLUGIN_RE.search(text or "")) or bool(ids_of(text or ""))


def discover_archive_rel(tasks_root: Path, *, skip_rel: str | None = None) -> str | None:
    skip = (skip_rel or "").replace("\\", "/")
    found: list[str] = []
    for path in sorted(tasks_root.rglob("*.md")):
        if ".rsync-backup" in path.parts:
            continue
        rel = path.relative_to(tasks_root).as_posix()
        if rel == skip:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if looks_like_archive(text):
            found.append(rel)
    if not found:
        return None
    # Prefer a top-level archive over nested notes.
    found.sort(key=lambda r: (r.count("/"), len(r), r))
    return found[0]


def drop_task_blocks(content: str, drop_ids: Iterable[str]) -> tuple[str, int]:
    """Remove whole kanban cards whose task id is in drop_ids. Keep header/footer."""
    wanted = {i.lower() for i in drop_ids if i}
    if not wanted:
        return content, 0
    ended_nl = content.endswith("\n")
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    dropped = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not TASK_START_RE.match(line):
            out.append(line)
            i += 1
            continue
        block = [line]
        i += 1
        while i < n:
            nxt = lines[i]
            if TASK_START_RE.match(nxt) or nxt.startswith("## ") or nxt.startswith("%%"):
                break
            if nxt.startswith("\t") or nxt.startswith("    ") or not nxt.strip():
                block.append(nxt)
                i += 1
                continue
            break
        block_text = "\n".join(block)
        match = ID_RE.search(block_text)
        tid = match.group(1).lower() if match else ""
        if tid and tid in wanted:
            dropped += 1
            while out and out[-1] == "":
                out.pop()
            continue
        out.extend(block)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if ended_nl and not text.endswith("\n"):
        text += "\n"
    return text, dropped


@dataclass
class BoardProtectPlan:
    drop_ids: set[str]
    new_local_text: str
    dropped: int
    genuine_local: set[str]
    missing_real: set[str]
    protect: bool
    skip_force_push: bool
    log_lines: list[str] = field(default_factory=list)


def plan_board_protect(
    local_board: str,
    server_board: str,
    archive_text: str,
) -> BoardProtectPlan:
    archive_ids = ids_of(archive_text)
    local_ids = ids_of(local_board)
    server_ids = ids_of(server_board)
    drop_ids = local_ids & archive_ids
    new_text, dropped = drop_task_blocks(local_board, drop_ids)
    new_ids = ids_of(new_text)
    genuine = new_ids - server_ids - archive_ids
    missing_on_local = server_ids - new_ids
    missing_archived = missing_on_local & archive_ids
    missing_real = missing_on_local - archive_ids
    # Fat local after a successful archive: extras are already in archive_text.
    # After strip, local matches server (+ genuine creates). Pull the thin board
    # unless we still have local-only creates or need to overwrite a fat server.
    protect = bool(genuine) or bool(missing_archived)
    skip_force_push = bool(missing_real) and len(missing_real) > INTENTIONAL_DELETE_MAX
    logs: list[str] = []
    if dropped:
        logs.append(f"strip archived duplicates from board: {dropped}")
    if genuine:
        logs.append(f"keep {len(genuine)} genuine local-only task id(s)")
    if missing_archived and not genuine:
        logs.append(
            f"push cleaned board: drop {len(missing_archived)} archived id(s) still on server board"
        )
    if skip_force_push:
        logs.append(
            f"skip force_push board: would drop {len(missing_real)} server task id(s)"
        )
    return BoardProtectPlan(
        drop_ids=drop_ids,
        new_local_text=new_text,
        dropped=dropped,
        genuine_local=genuine,
        missing_real=missing_real,
        protect=protect,
        skip_force_push=skip_force_push,
        log_lines=logs,
    )


def _ssh_cat(server: str, remote_path: str, timeout: int = 20) -> str | None:
    quoted = "'" + remote_path.replace("'", "'\"'\"'") + "'"
    try:
        proc = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                server,
                f"cat {quoted}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _write_if_changed(path: Path, new_text: str, old_text: str) -> bool:
    if new_text == old_text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def cmd_filter_force_push(args: argparse.Namespace) -> int:
    list_file = Path(args.list_file)
    tasks_root = Path(args.tasks_root)
    server = args.server
    server_tasks = args.server_tasks.rstrip("/")
    archive_rel = args.archive_rel or discover_archive_rel(tasks_root)
    archive_text = ""
    if archive_rel:
        remote_archive = _ssh_cat(server, f"{server_tasks}/{archive_rel}")
        if remote_archive is not None:
            archive_text = remote_archive
        else:
            local_archive = tasks_root / archive_rel
            try:
                archive_text = local_archive.read_text(encoding="utf-8")
            except OSError:
                archive_text = ""

    lines = [ln.strip() for ln in list_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    keep: list[str] = []
    removed = 0
    for rel in lines:
        local_path = tasks_root / rel
        try:
            local_text = local_path.read_text(encoding="utf-8")
        except OSError:
            keep.append(rel)
            continue
        local_ids = ids_of(local_text)
        if not local_ids or not rel.endswith(".md"):
            keep.append(rel)
            continue
        server_text = _ssh_cat(server, f"{server_tasks}/{rel}")
        if server_text is None:
            keep.append(rel)
            continue
        if looks_like_board(local_text) and archive_text:
            plan = plan_board_protect(local_text, server_text, archive_text)
            for line in plan.log_lines:
                print(f"{rel}: {line}", file=sys.stderr)
            _write_if_changed(local_path, plan.new_local_text, local_text)
            if plan.skip_force_push:
                removed += 1
                continue
            keep.append(rel)
            continue
        server_ids = ids_of(server_text)
        missing_on_local = server_ids - local_ids
        if missing_on_local and len(missing_on_local) > INTENTIONAL_DELETE_MAX:
            removed += 1
            print(
                f"skip force_push {rel}: would drop {len(missing_on_local)} server task id(s)",
                file=sys.stderr,
            )
            continue
        if missing_on_local:
            print(
                f"allow force_push {rel}: drop {len(missing_on_local)} id(s) as intentional delete(s)",
                file=sys.stderr,
            )
        keep.append(rel)

    list_file.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    print(len(keep))
    if removed:
        print(f"filtered_force_push removed={removed}", file=sys.stderr)
    return 0


def cmd_pull_protect(args: argparse.Namespace) -> int:
    tasks_root = Path(args.tasks_root)
    out_file = Path(args.out_file)
    server = args.server
    server_tasks = args.server_tasks.rstrip("/")
    archive_rel = args.archive_rel or discover_archive_rel(tasks_root)
    archive_text = ""
    if archive_rel:
        remote_archive = _ssh_cat(server, f"{server_tasks}/{archive_rel}")
        if remote_archive is not None:
            archive_text = remote_archive
        else:
            local_archive = tasks_root / archive_rel
            try:
                archive_text = local_archive.read_text(encoding="utf-8")
            except OSError:
                archive_text = ""

    excludes: list[str] = []
    for path in tasks_root.rglob("*.md"):
        if ".rsync-backup" in path.parts:
            continue
        try:
            local_text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        local_ids = ids_of(local_text)
        if len(local_ids) < 3:
            continue
        rel = path.relative_to(tasks_root).as_posix()
        server_text = _ssh_cat(server, f"{server_tasks}/{rel}")
        if server_text is None:
            continue
        if looks_like_board(local_text) and archive_text:
            plan = plan_board_protect(local_text, server_text, archive_text)
            for line in plan.log_lines:
                print(f"{rel}: {line}", file=sys.stderr)
            _write_if_changed(path, plan.new_local_text, local_text)
            if plan.protect:
                excludes.append(rel)
                print(
                    f"protect pull {rel}: keep {len(plan.genuine_local)} local-only, "
                    f"strip {plan.dropped} archived",
                    file=sys.stderr,
                )
            continue
        server_ids = ids_of(server_text)
        only_local = local_ids - server_ids
        if only_local:
            excludes.append(rel)
            print(
                f"protect pull {rel}: keep {len(only_local)} local-only task id(s)",
                file=sys.stderr,
            )

    out_file.write_text("\n".join(excludes) + ("\n" if excludes else ""), encoding="utf-8")
    print(len(excludes))
    return 0


def strip_board_duplicates(board_text: str, archive_text: str) -> tuple[str, int]:
    drop_ids = ids_of(board_text) & ids_of(archive_text)
    return drop_task_blocks(board_text, drop_ids)


def cmd_strip_local(args: argparse.Namespace) -> int:
    board = Path(args.board)
    archive = Path(args.archive)
    local_text = board.read_text(encoding="utf-8")
    archive_text = archive.read_text(encoding="utf-8")
    new_text, dropped = strip_board_duplicates(local_text, archive_text)
    if args.dry_run:
        print(f"would_strip={dropped}")
        return 0
    _write_if_changed(board, new_text, local_text)
    print(f"stripped={dropped}")
    return 0


def cmd_strip_dir(args: argparse.Namespace) -> int:
    tasks_root = Path(args.tasks_root)
    archive_rel = args.archive_rel or discover_archive_rel(tasks_root)
    if not archive_rel:
        print("stripped=0")
        return 0
    archive_path = tasks_root / archive_rel
    try:
        archive_text = archive_path.read_text(encoding="utf-8")
    except OSError:
        print("stripped=0")
        return 0
    dropped_total = 0
    for path in tasks_root.rglob("*.md"):
        if ".rsync-backup" in path.parts:
            continue
        rel = path.relative_to(tasks_root).as_posix()
        if rel == archive_rel:
            continue
        try:
            local_text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not looks_like_board(local_text):
            continue
        new_text, dropped = strip_board_duplicates(local_text, archive_text)
        if dropped:
            if not args.dry_run:
                _write_if_changed(path, new_text, local_text)
            dropped_total += dropped
            print(f"strip {rel}: {dropped}", file=sys.stderr)
    print(f"stripped={dropped_total}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_fp = sub.add_parser("filter-force-push")
    p_fp.add_argument("--list-file", required=True)
    p_fp.add_argument("--tasks-root", required=True)
    p_fp.add_argument("--server", required=True)
    p_fp.add_argument("--server-tasks", required=True)
    p_fp.add_argument("--archive-rel", default="")
    p_fp.set_defaults(func=cmd_filter_force_push)

    p_pp = sub.add_parser("pull-protect")
    p_pp.add_argument("--tasks-root", required=True)
    p_pp.add_argument("--out-file", required=True)
    p_pp.add_argument("--server", required=True)
    p_pp.add_argument("--server-tasks", required=True)
    p_pp.add_argument("--archive-rel", default="")
    p_pp.set_defaults(func=cmd_pull_protect)

    p_st = sub.add_parser("strip-local")
    p_st.add_argument("--board", required=True)
    p_st.add_argument("--archive", required=True)
    p_st.add_argument("--dry-run", action="store_true")
    p_st.set_defaults(func=cmd_strip_local)

    p_sd = sub.add_parser("strip-dir")
    p_sd.add_argument("--tasks-root", required=True)
    p_sd.add_argument("--archive-rel", default="")
    p_sd.add_argument("--dry-run", action="store_true")
    p_sd.set_defaults(func=cmd_strip_dir)

    args = ap.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
