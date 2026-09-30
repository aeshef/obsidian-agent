from __future__ import annotations

from pathlib import Path
from typing import List

from shared.domain_messages import dmsg
from shared.locale import agent_locale
from shared.yaml_config import load_yaml_list_runtime
from bot.config_loader import get_nlu_config

ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = str(ROOT / "config")


def load_categories(kind: str = "expense") -> List[str]:
    base = "income_categories" if kind == "income" else "categories_mvp"
    loc = agent_locale().strip().lower()
    suffix = "en" if loc.startswith("en") else "ru"
    # Personal lists take precedence over bundled locale examples.
    stems = (f"{base}.{suffix}", base)
    ordered = [stem for stem in stems if (Path(_CONFIG_DIR) / f"{stem}.yaml").is_file()]
    ordered += [stem for stem in stems if stem not in ordered]
    for stem in ordered:
        data = load_yaml_list_runtime(_CONFIG_DIR, stem)
        if data:
            # Broker handlers and NLU must accept the same configured labels.
            broker = get_nlu_config().get("broker_categories", {})
            roles = ("withdraw",) if kind == "income" else ("topup", "fee")
            labels = [broker.get(role) for role in roles]
            return list(dict.fromkeys(data + [label.strip() for label in labels if isinstance(label, str) and label.strip()]))
    raise FileNotFoundError(
        dmsg("finance", "categories_file_missing", path=f"{_CONFIG_DIR}/{base}.{suffix}.yaml")
    )
