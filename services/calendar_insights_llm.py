from planning_bot.core.pdmsg import pdmsg
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _read_cache(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug("insights cache read: %s", e)
    return {}


def _write_cache(path: Path, stats_hash: str, insights_md: str, at: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"stats_hash": stats_hash, "insights_md": insights_md, "at": at},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        logger.warning("insights cache write: %s", e)


def generate_calendar_insights(analytics: Dict[str, Any]) -> Optional[str]:
    'Operation implementation.'
    try:
        from planning_bot.core.llm import DeepSeekClient
        from planning_bot.core.settings import get_config_path, load_prompt
    except Exception as e:
        logger.debug("calendar insights: import %s", e)
        return None

    try:
        client = DeepSeekClient()
    except Exception as e:
        logger.info(pdmsg("auto_adb9a2ca8d"), e)
        return None

    try:
        system = load_prompt(get_config_path(), "calendar_week_insights")
    except Exception as e:
        logger.warning(pdmsg("auto_57bd906864"), e)
        return None

    payload = json.dumps(analytics, ensure_ascii=False, indent=2)
    if len(payload) > 12000:
        payload = payload[:12000] + "\n…"

    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                pdmsg("auto_aaa9da396d", payload={payload})
            ),
        },
    ]
    try:
        text = client.chat(messages, temperature=0.45, max_retries=2)
    except Exception as e:
        logger.warning("calendar insights: API %s", e)
        return None

    t = (text or "").strip()
    if not t:
        return None
    lines = [ln for ln in t.splitlines() if not ln.strip().startswith("# ")]
    return "\n".join(lines).strip()


def get_or_create_insights(
    analytics: Dict[str, Any],
    cache_path: Path,
    stats_hash: str,
    now_iso: str,
) -> Tuple[str, bool]:
    'Operation implementation.'
    c = _read_cache(cache_path)
    if c.get("stats_hash") == stats_hash and (c.get("insights_md") or "").strip():
        return str(c["insights_md"]).strip(), True

    md = generate_calendar_insights(analytics)
    if md:
        _write_cache(cache_path, stats_hash, md, now_iso)
        return md, False

    fb = (
        pdmsg("auto_93d0c33a86")
    )
    return fb, False
