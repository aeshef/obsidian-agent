"""Idempotent .env hints for enabled connectors — never overwrites existing values."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping

# Keys to suggest when a connector is on (values left empty for the user).
_CONNECTOR_ENV_HINTS: dict[str, tuple[str, ...]] = {
    "broker_sync": ("TINKOFF_API_TOKEN=",),
    "gmail_health_pipeline": (
        "GMAIL_IMAP_USER=",
        "GMAIL_IMAP_APP_PASSWORD=",
    ),
    "corporate_badge": (),
    "domestic_bank_cards": (),
}

_CORE_HINTS = (
    "VAULT_PATH=",
    "TELEGRAM_UNIFIED_BOT_TOKEN=",
    "DEEPSEEK_API_KEY=",
)

_MODULE_ENV_HINTS: dict[str, tuple[str, ...]] = {
    "finance": (),
    "planning": ("TELEGRAM_PLANNING_BOT_TOKEN=",),
    "knowledge": (
        "TELEGRAM_KNOWLEDGE_BOT_TOKEN=",
        "TELEGRAM_USER_ID=",
    ),
}


def _key_from_line(line: str):
    m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
    return m.group(1) if m else None


def _line_has_value(line: str) -> bool:
    if "=" not in line:
        return False
    _, _, val = line.partition("=")
    return bool(val.strip().strip('"').strip("'"))


def collect_env_hints(
    connectors: Mapping[str, bool],
    *,
    modules: Mapping[str, bool] | None = None,
    include_core: bool = True,
) -> list[str]:
    lines: list[str] = []
    if include_core:
        lines.extend(_CORE_HINTS)
    if modules:
        for name, enabled in modules.items():
            if not enabled:
                continue
            lines.extend(_MODULE_ENV_HINTS.get(name, ()))
    for name, enabled in connectors.items():
        if not enabled:
            continue
        for hint in _CONNECTOR_ENV_HINTS.get(name, ()):
            lines.append(hint)
    return lines


def patch_env_file(
    path: Path,
    hints: Iterable[str],
    *,
    dry_run: bool = False,
) -> list[str]:
    """Append missing keys (no value) to .env. Returns lines added."""
    path = Path(path)
    existing_keys: set[str] = set()
    body: list[str] = []
    if path.is_file():
        body = path.read_text(encoding="utf-8").splitlines()
        for line in body:
            key = _key_from_line(line)
            if key:
                existing_keys.add(key)

    added: list[str] = []
    for hint in hints:
        key = _key_from_line(hint)
        if not key or key in existing_keys:
            continue
        added.append(hint)
        existing_keys.add(key)

    if not added or dry_run:
        return added

    if body and body[-1].strip():
        body.append("")
    body.append("# --- suggested by apply_capabilities_profile.py ---")
    body.extend(added)
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return added
