"""Parse and load vault signals config (editable markdown with YAML block)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from shared.routines_paths import signals_config_md_path, signals_config_yaml_legacy_path
from shared.yaml_config import load_yaml


def _yaml_from_markdown(text: str) -> dict[str, Any]:
    match = re.search(r"```yaml\s*\n([\s\S]*?)```", text)
    if not match:
        return {}
    import yaml

    raw = yaml.safe_load(match.group(1))
    return dict(raw) if isinstance(raw, dict) else {}


def load_vault_signals_config(vault_root: Path | None = None) -> dict[str, Any]:
    md_path = signals_config_md_path(vault_root)
    if md_path.is_file():
        cfg = _yaml_from_markdown(md_path.read_text(encoding="utf-8"))
        if cfg:
            return cfg
    legacy = signals_config_yaml_legacy_path(vault_root)
    if legacy.is_file():
        over = load_yaml(legacy, default={})
        return dict(over) if isinstance(over, dict) else {}
    return {}
