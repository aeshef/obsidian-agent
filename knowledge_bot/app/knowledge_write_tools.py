"""Allowlisted knowledge note append (env-gated; dry-run by default)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from shared.agent.tools import tool
from shared.agent.types import AgentContext
from shared.domain_messages import dmsg
from shared.paths import vault_root_optional
from shared.vault_layout import knowledge_subdir

_NS = ("knowledge_write",)
_FM_SPLIT = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _writes_enabled() -> bool:
    return (os.environ.get("KNOWLEDGE_AGENT_WRITES") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _safe_note_path(vault: Path, rel: str) -> Path | None:
    rel_n = (rel or "").strip().lstrip("/")
    if not rel_n or ".." in Path(rel_n).parts:
        return None
    # Must live under knowledge subdir.
    ksub = knowledge_subdir().strip("/").replace("\\", "/")
    norm = rel_n.replace("\\", "/")
    if ksub and not (norm == ksub or norm.startswith(ksub + "/")):
        # Allow relative path inside knowledge root
        candidate = vault / ksub / norm
    else:
        candidate = vault / norm
    try:
        resolved = candidate.resolve()
        root = (vault / ksub).resolve() if ksub else vault.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        return None
    if resolved.suffix.lower() != ".md":
        return None
    return resolved


@tool(category="notes")
async def append_knowledge_note(
    ctx: AgentContext,
    rel_path: str,
    text: str,
    dry_run: bool = True,
) -> str:
    """Append a short paragraph to an existing knowledge note. Requires KNOWLEDGE_AGENT_WRITES=1. dry_run=true previews only."""
    if not _writes_enabled():
        return dmsg(*_NS, "disabled")
    body = (text or "").strip()
    if not body:
        return dmsg(*_NS, "empty_text")
    if len(body) > 2000:
        body = body[:2000]
    vault = vault_root_optional()
    if vault is None:
        return dmsg(*_NS, "vault_missing")
    path = _safe_note_path(vault, rel_path)
    if path is None:
        return dmsg(*_NS, "bad_path", path=rel_path or "-")
    if not path.is_file():
        return dmsg(*_NS, "missing", path=str(path.relative_to(vault.resolve())))
    try:
        rel = path.resolve().relative_to(vault.resolve()).as_posix()
    except ValueError:
        rel = path.name
    snippet = body if body.endswith("\n") else body + "\n"
    if dry_run:
        return dmsg(*_NS, "dry_run", path=rel, chars=len(snippet))
    raw = path.read_text(encoding="utf-8")
    if _FM_SPLIT.match(raw):
        new_raw = raw.rstrip() + "\n\n" + snippet
    else:
        new_raw = raw.rstrip() + "\n\n" + snippet
    path.write_text(new_raw, encoding="utf-8")
    return dmsg(*_NS, "ok", path=rel, chars=len(snippet))
