"""Vault-relative paths from config/agent/platform.yaml or env (no personal defaults in code)."""
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger("vault_layout")


def _strip_slashes(rel: str) -> str:
    return rel.strip().strip("/")


def knowledge_subdir() -> str:
    """Knowledge base directory relative to VAULT_PATH (e.g. Knowledge or 700_…)."""
    from shared.agent.platform_config import platform_value

    return _strip_slashes(
        platform_value(
            "vault",
            "knowledge_subdir",
            env="VAULT_REL_KNOWLEDGE",
            default="Knowledge",
        )
    )


def knowledge_index_roots() -> list[str]:
    """Vault-relative dirs to scan for the note index (read/search).

    Always includes ``knowledge_subdir`` (write root). Extra roots come from
    ``vault.knowledge_index_extra_folders`` as keys into ``vault_paths.folders``
    (e.g. ``handwritten`` → vault handwritten folder). Writes stay on knowledge_subdir only.
    """
    from shared.agent.platform_config import platform_value
    from shared.vault_paths_config import folder

    roots: list[str] = []
    primary = knowledge_subdir()
    if primary:
        roots.append(primary)

    raw = platform_value("vault", "knowledge_index_extra_folders", default=None)
    if isinstance(raw, str):
        keys = [p.strip() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        keys = [str(x).strip() for x in raw if str(x).strip()]
    else:
        keys = []

    seen = set(roots)
    for key in keys:
        try:
            rel = _strip_slashes(folder(key))
        except Exception as e:
            log.warning("knowledge_index_extra_folders: skip %r (%s)", key, e)
            continue
        if not rel or rel in seen:
            continue
        seen.add(rel)
        roots.append(rel)
    return roots


def knowledge_attachments_subdir() -> str:
    """Attachments folder under knowledge_subdir (config/vault_paths.yaml)."""
    from shared.vault_paths_config import vault_rel_path

    return vault_rel_path("knowledge_attachments")


def knowledge_index_prefix() -> str:
    """rel_path prefix in note index (with trailing /)."""
    d = knowledge_subdir()
    return f"{d}/" if d else ""


def knowledge_path_pattern() -> re.Pattern[str]:
    """For JSON salvage: optional knowledge directory prefix in path strings."""
    sub = re.escape(knowledge_subdir())
    tail = r'[^"\],]{2,240})(?:"|,|\]|\s*$)'
    if sub:
        return re.compile('"((?:' + sub + r'/)?' + tail)
    return re.compile(r'"(' + tail)
