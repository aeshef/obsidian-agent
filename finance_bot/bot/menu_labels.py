"""Finance reply-menu labels (config/messages.{locale}.yaml → finance.menu)."""
from __future__ import annotations

from functools import lru_cache

from bot.ui import fin_menu


@lru_cache(maxsize=1)
def finance_menu_texts() -> dict[str, str]:
    return {
        "invest": fin_menu("invest"),
        "balance": fin_menu("balance"),
        "last_ops": fin_menu("last_ops"),
        "plan": fin_menu("plan"),
    }


def finance_menu_aliases() -> dict[str, str]:
    """Alias button text → canonical label (nlu_config.menu_aliases or *_short keys)."""
    from bot.config_loader import get_nlu_config

    cfg = get_nlu_config()
    raw = cfg.get("menu_aliases")
    if isinstance(raw, dict) and raw:
        canonical = finance_menu_texts()
        out: dict[str, str] = {}
        for alias, target in raw.items():
            a, t = str(alias).strip(), str(target).strip()
            if t in canonical:
                out[a] = canonical[t]
            elif t in canonical.values():
                out[a] = t
        return out

    canonical = finance_menu_texts()
    from shared.i18n import msg_raw

    menu = msg_raw("finance", "menu")
    if not isinstance(menu, dict):
        return {}
    out: dict[str, str] = {}
    for key, label in menu.items():
        if not str(key).endswith("_short"):
            continue
        base = str(key)[: -len("_short")]
        if base in canonical and isinstance(label, str) and label.strip():
            out[label.strip()] = canonical[base]
    return out
