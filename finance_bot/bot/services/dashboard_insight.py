"""Cached LLM tips for the finance Obsidian dashboard (month headroom narrative)."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("finance.dashboard_insight")


def _prompt_path() -> Path:
    from bot.config_loader import CONFIG_DIR

    live = CONFIG_DIR / "prompts" / "dashboard_month_insight.txt"
    if live.is_file():
        return live
    return CONFIG_DIR / "prompts" / "dashboard_month_insight.example.txt"


def _cache_path(vault: Path) -> Path:
    from bot.vault_paths import VaultPaths

    return VaultPaths(vault).finance_data_dir() / "finance_month_insight.json"


def _facts_hash(facts: dict[str, Any]) -> str:
    payload = json.dumps(facts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _read_cache(path: Path) -> dict[str, Any]:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.debug("insight cache read: %s", e)
    return {}


def _write_cache(path: Path, doc: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("insight cache write: %s", e)


def _enabled() -> bool:
    try:
        from shared.agent.platform_config import platform_int

        return bool(platform_int("finance_dashboard_insight", "enabled", default=1))
    except Exception:
        return True


def _fallback_cached_markdown(cached: dict[str, Any], day: str) -> str:
    """Reuse same-day cached tip if LLM is unreachable (proxy/DNS)."""
    if cached.get("day") == day and (cached.get("markdown") or "").strip():
        return str(cached["markdown"]).strip()
    return ""


def generate_dashboard_month_insight(
    vault: Path,
    facts: dict[str, Any],
    *,
    force: bool = False,
) -> str:
    """Return Obsidian callout markdown, or empty string if disabled/unavailable."""
    if not _enabled():
        return ""

    prompt_file = _prompt_path()
    if not prompt_file.is_file():
        return ""

    cache = _cache_path(vault)
    h = _facts_hash(facts)
    day = datetime.now().strftime("%Y-%m-%d")
    cached = _read_cache(cache)
    if (
        not force
        and cached.get("day") == day
        and cached.get("facts_hash") == h
        and (cached.get("markdown") or "").strip()
    ):
        return str(cached["markdown"]).strip()

    try:
        from bot.llm import LLMClient
    except Exception as e:
        log.debug("dashboard insight import: %s", e)
        return _fallback_cached_markdown(cached, day)

    client = LLMClient()
    if not getattr(client, "api_key", None):
        return _fallback_cached_markdown(cached, day)

    system = prompt_file.read_text(encoding="utf-8").strip()
    user = json.dumps(facts, ensure_ascii=False, indent=2)
    try:
        text = client.chat_messages(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.35,
            max_retries=1,
            raise_on_error=True,
        )
    except Exception as e:
        log.warning("dashboard insight LLM: %s", e)
        return _fallback_cached_markdown(cached, day)

    md = (text or "").strip()
    if not md:
        return ""
    # Drop leading H1 if model adds one
    lines = [ln for ln in md.splitlines() if not ln.strip().startswith("# ")]
    md = "\n".join(lines).strip()
    if not md.startswith(">"):
        # Soft-wrap as tip callout if model returned plain bullets
        body = "\n".join(f"> {ln}" if ln.strip() else ">" for ln in md.splitlines())
        md = f"> [!tip] Month tips\n{body}"

    _write_cache(
        cache,
        {"day": day, "facts_hash": h, "at": datetime.now().isoformat(timespec="seconds"), "markdown": md},
    )
    return md
