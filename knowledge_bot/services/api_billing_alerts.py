"""Telegram alerts for API billing/quota errors (deduplicated by service + error class)."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("kb.api_alerts")

_KB = Path(__file__).resolve().parent.parent
_STATE = _KB / "data" / "api_billing_alerts_state.json"
_COOLDOWN = int(os.environ.get("API_BILLING_ALERT_COOLDOWN_SEC", str(4 * 3600)))


def _state_path() -> Path:
    p = _KB / "data"
    p.mkdir(parents=True, exist_ok=True)
    return _STATE


def _load_state() -> dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return {"last": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"last": {}}


def _save_state(st: dict[str, Any]) -> None:
    try:
        _state_path().parent.mkdir(parents=True, exist_ok=True)
        _state_path().write_text(json.dumps(st, ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError as e:
        log.warning("api_billing_alerts: cannot save state: %s", e)


def _throttle_key(service: str, status: int, body: str) -> str:
    """Helper."""
    b = (body or "").lower()
    if status == 402 or "insufficient" in b or "balance" in b and "low" in b:
        return f"{service}:pay_or_balance"
    if status == 429 and ("quota" in b or "exceeded" in b):
        return f"{service}:quota_429"
    if status in (401, 403) and any(x in b for x in ("invalid", "key", "unauthorized", "forbidden")):
        return f"{service}:auth_{status}"
    return f"{service}:http_{status}"


def _should_send(key: str) -> bool:
    st = _load_state()
    last: dict = st.get("last") or {}
    now = time.time()
    prev = last.get(key)
    if prev is not None and (now - float(prev)) < _COOLDOWN:
        return False
    last[key] = now
    st["last"] = last
    _save_state(st)
    return True


def is_likely_billing_or_quota_error(status: int, body: str) -> bool:
    """True when user should be notified (billing/quota, not plain RPS rate limit)."""
    if status == 200:
        return False
    t = (body or "").lower()
    if status == 402:
        return True
    if "payment required" in t or "insufficient" in t and "credit" in t:
        return True
    if "insufficient balance" in t or "out of credits" in t or "not enough credit" in t:
        return True
    if "quota exceeded" in t or "exceeded your" in t and "quota" in t:
        return True
    if "rate limit" in t and "purchase" in t:
        return True
    if status == 429:
        if any(
            w in t
            for w in (
                "quota",
                "exceeded",
                "insufficient",
                "balance",
                "credit",
                "billing",
                "payment",
            )
        ):
            return True
        return False
    if status in (400, 401, 403):
        if any(
            w in t
            for w in (
                "balance",
                "billing",
                "payment",
                "credit",
                "quota",
                "exceeded",
            )
        ):
            return True
    return False


def _html_escape(s: str, max_len: int = 400) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def _short_detail(body: str) -> str:
    t = (body or "").strip()
    if not t:
        return "—"
    try:
        j = json.loads(t)
        if isinstance(j, dict):
            err = j.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])[:500]
            if j.get("message"):
                return str(j["message"])[:500]
    except Exception:
        pass
    one = re.sub(r"\s+", " ", t)
    return one[:500] if len(one) > 500 else one


def send_billing_alert_if_needed(
    service_label: str,
    status: int,
    body: str,
) -> None:
    """Send Telegram alert via HTTP (api.telegram.org), without aiogram."""
    if not is_likely_billing_or_quota_error(status, body):
        return
    key = _throttle_key(service_label, status, body)
    if not _should_send(key):
        log.debug("api_billing_alerts: throttled %s", key)
        return
    from knowledge_bot.core.config import load_config

    cfg = load_config()
    token = (cfg.telegram_bot_token or "").strip()
    uid = cfg.telegram_user_id
    if not token or not uid:
        log.warning(
            "api_billing_alerts: no telegram token or user id in config (unified/finance/knowledge), skip"
        )
        return
    base = (cfg.telegram_api_base or "https://api.telegram.org").rstrip("/")
    url = f"{base}/bot{token}/sendMessage"
    detail = _html_escape(_short_detail(body))
    from knowledge_bot.i18n.domain_text import billing

    text = (
        billing("alert_header")
        + billing("alert_service", service=_html_escape(service_label, 80))
        + f"HTTP: <code>{status}</code>\n\n"
        + billing("alert_body")
        + "\n\n"
        + billing("alert_detail", detail=detail)
    )
    try:
        r = requests.post(
            url,
            json={"chat_id": uid, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
        if not r.ok:
            log.error("api_billing_alerts: Telegram sendMessage failed %s: %s", r.status_code, (r.text or "")[:200])
        else:
            log.info("api_billing_alerts: sent for %s %s", service_label, status)
    except Exception as e:
        log.exception("api_billing_alerts: send failed: %s", e)
