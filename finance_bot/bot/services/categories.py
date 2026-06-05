from __future__ import annotations

from pathlib import Path
from typing import List

from shared.domain_messages import dmsg
from shared.locale import agent_locale
from shared.yaml_config import load_yaml_list_runtime

ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = str(ROOT / "config")


def load_categories(kind: str = "expense") -> List[str]:
    base = "income_categories" if kind == "income" else "categories_mvp"
    loc = agent_locale().strip().lower()
    suffix = "en" if loc.startswith("en") else "ru"
    for stem in (f"{base}.{suffix}", base):
        data = load_yaml_list_runtime(_CONFIG_DIR, stem)
        if data:
            return data
    raise FileNotFoundError(
        dmsg("finance", "categories_file_missing", path=f"{_CONFIG_DIR}/{base}.{suffix}.yaml")
    )
