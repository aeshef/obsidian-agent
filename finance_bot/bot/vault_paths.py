"""
Obsidian vault paths for the finance bot and scripts.

Folder/file name segments come from config/vault_paths.yaml; override via env
(FINANCE_REL_* — path segments relative to vault root, no leading /).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from shared.paths import vault_root_optional as _shared_vault_root_optional
from shared.vault_paths_config import dashboards_sub, finance_sub, folder


def _seg(env_key: str, default: str) -> str:
    v = os.environ.get(env_key, "").strip().strip("/")
    if v and (".." in v or v.startswith("/") or "\\" in v):
        v = ""
    return v if v else default


def vault_root_optional() -> Optional[Path]:
    """Vault root via shared.paths (VAULT_PATH / configured local vault)."""
    return _shared_vault_root_optional()


class VaultPaths:
    """All derived paths from vault root."""

    __slots__ = ("root",)

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def dashboards_dir(self) -> Path:
        return self.root / _seg("FINANCE_REL_DASHBOARDS", folder("dashboards"))

    def finance_data_dir(self) -> Path:
        return self.dashboards_dir() / _seg("FINANCE_REL_DATA", dashboards_sub("data"))

    def finance_db(self, filename: str = "finance.db") -> Path:
        return self.finance_data_dir() / filename

    def finance_dashboard_md(self) -> Path:
        name = _seg("FINANCE_REL_DASHBOARD_MD", finance_sub("dashboard_md"))
        return self.dashboards_dir() / name

    def finance_charts_dir(self) -> Path:
        g = _seg("FINANCE_REL_GRAPHS", dashboards_sub("charts"))
        sub = _seg("FINANCE_REL_GRAPHS_FINANCE", finance_sub("graphs_finance"))
        return self.dashboards_dir() / g / sub

    def portfolio_meta_dir(self) -> Path:
        rel = _seg("FINANCE_REL_META", finance_sub("meta"))
        return self.root.joinpath(*rel.split("/"))

    def portfolio_log_file(self) -> Path:
        name = _seg("FINANCE_REL_PORTFOLIO_LOG_NAME", finance_sub("portfolio_log"))
        return self.portfolio_meta_dir() / name

    def portfolio_cache_note(self) -> Path:
        name = _seg("FINANCE_REL_PORTFOLIO_CACHE_NAME", finance_sub("portfolio_cache"))
        return self.portfolio_meta_dir() / name

    def trash_dir(self) -> Path:
        arch = _seg("FINANCE_REL_ARCHIVE", folder("archive"))
        return self.root / arch / "Trash"

    def legacy_automation_env(self) -> Path:
        auto = _seg("FINANCE_REL_AUTOMATION", folder("automation"))
        return self.root / auto / ".env"

    def tg_alerting_import_root(self) -> Path:
        raw = os.environ.get("FINANCE_TG_ALERTING_ROOT", "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
        return self.root

    def optional_python_env_bin(self) -> Optional[Path]:
        auto = _seg("FINANCE_REL_AUTOMATION", folder("automation"))
        env_bin = self.root / auto / "env" / "bin"
        return env_bin if env_bin.is_dir() else None
