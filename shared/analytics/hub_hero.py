"""Hero callouts for vault hub dashboards (one number + short context, no sparklines)."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Callable

from shared.chart_paths import data_path
from shared.vault_paths_config import folder


def _safe_msg(msg: Callable[..., str], key: str, **kwargs: Any) -> str:
    try:
        text = msg(key, **kwargs) if kwargs else msg(key)
    except TypeError:
        try:
            text = msg(key)
        except Exception:
            return ""
    except Exception:
        return ""
    if not text or text == key:
        return ""
    return str(text).strip()


def load_life_os_last(vault: Path) -> dict[str, Any] | None:
    path = data_path(vault, "life_os_daily_json")
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rows = raw.get("rows") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    last = rows[-1]
    for row in reversed(rows):
        if isinstance(row, dict) and row.get("regime"):
            last = row
            break
    return last if isinstance(last, dict) else None


def load_panel_last(vault: Path) -> dict[str, str] | None:
    path = data_path(vault, "master_daily_panel_csv")
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return None
    return rows[-1] if rows else None


def _parse_agent_cost_md(vault: Path) -> dict[str, str]:
    """Best-effort scrape from generated agent cost companion note."""
    from shared.chart_paths import chart_path

    candidates: list[Path] = []
    try:
        candidates.append(chart_path(vault, "agent_cost_dashboard_md"))
    except Exception:
        pass
    for rel in (
        "Charts/System/Agent_cost.md",
    ):
        candidates.append(vault / folder("dashboards") / rel)
    text = ""
    for p in candidates:
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8")
                break
            except OSError:
                continue
    if not text:
        return {}
    out: dict[str, str] = {}
    m = re.search(r"estimate\s+\*\*\$([0-9.]+)\*\*", text, re.I)
    if not m:
        m = re.search(r"\$([0-9]+\.[0-9]+)", text)
    if m:
        out["cost_usd"] = m.group(1)
    m = re.search(r"Runs\s+\*\*(\d+)\*\*", text, re.I)
    if not m:
        m = re.search(r"\| Runs \| (\d+) \|", text)
    if m:
        out["runs"] = m.group(1)
    m = re.search(r"Usage coverage \| ([0-9.]+)%", text, re.I)
    if m:
        out["usage_pct"] = m.group(1)
    return out


def render_analytics_hero(vault: Path, msg: Callable[..., str]) -> str:
    last = load_life_os_last(vault)
    if not last:
        empty = _safe_msg(msg, "analytics_hero_empty")
        return empty + "\n" if empty else ""
    regime = str(last.get("regime") or "?")
    regime_label = _safe_msg(msg, f"analytics_regime_{regime}") or regime
    debt = last.get("sleep_debt")
    debt_s = f"{float(debt):.1f}" if debt is not None else "—"
    cap = last.get("capacity")
    out = last.get("output")
    drain = last.get("drain")
    lines = [
        _safe_msg(msg, "analytics_hero_open") or "> [!abstract] Today",
        _safe_msg(
            msg,
            "analytics_hero_title",
            regime=regime_label,
            debt=debt_s,
        )
        or f"> ### {regime_label} · sleep debt {debt_s} h",
        _safe_msg(
            msg,
            "analytics_hero_meta",
            capacity=int(round(float(cap))) if cap is not None else "—",
            output=int(round(float(out))) if out is not None else "—",
            drain=int(round(float(drain))) if drain is not None else "—",
        )
        or f"> Capacity **{cap}** · Output **{out}** · Drain **{drain}**",
        _safe_msg(msg, "analytics_hero_updated", date=str(last.get("date") or ""))
        or f"> _{last.get('date')}_",
    ]
    return "\n".join(x for x in lines if x) + "\n"


def render_health_hero(vault: Path, msg: Callable[..., str]) -> str:
    row = load_panel_last(vault)
    if not row:
        empty = _safe_msg(msg, "health_hero_empty")
        return empty + "\n" if empty else ""
    steps = row.get("iphone_steps") or row.get("steps") or "—"
    kcal = row.get("iphone_active_calories_kcal") or row.get("kcal") or "—"
    weight = row.get("iphone_weight_kg") or "—"
    sleep = row.get("iphone_sleep_hours") or "—"
    try:
        steps_s = f"{int(float(steps)):,}".replace(",", " ")
    except (TypeError, ValueError):
        steps_s = str(steps)
    try:
        kcal_s = f"{int(float(kcal))}"
    except (TypeError, ValueError):
        kcal_s = str(kcal)
    try:
        weight_s = f"{float(weight):.1f}"
    except (TypeError, ValueError):
        weight_s = str(weight)
    try:
        sleep_s = f"{float(sleep):.1f}"
    except (TypeError, ValueError):
        sleep_s = str(sleep)
    lines = [
        _safe_msg(msg, "health_hero_open") or "> [!abstract] Latest day",
        _safe_msg(msg, "health_hero_title", steps=steps_s) or f"> ### {steps_s} steps",
        _safe_msg(
            msg,
            "health_hero_meta",
            kcal=kcal_s,
            weight=weight_s,
            sleep=sleep_s,
        )
        or f"> Active **{kcal_s}** kcal · weight **{weight_s}** kg · sleep **{sleep_s}** h",
        _safe_msg(msg, "health_hero_updated", date=str(row.get("date") or ""))
        or f"> _{row.get('date')}_",
    ]
    return "\n".join(x for x in lines if x) + "\n"


def render_system_hero(vault: Path, msg: Callable[..., str]) -> str:
    scraped = _parse_agent_cost_md(vault)
    if not scraped:
        empty = _safe_msg(msg, "system_hero_empty")
        return empty + "\n" if empty else ""
    cost = scraped.get("cost_usd", "—")
    runs = scraped.get("runs", "—")
    usage = scraped.get("usage_pct", "—")
    lines = [
        _safe_msg(msg, "system_hero_open") or "> [!abstract] Agent window",
        _safe_msg(msg, "system_hero_title", cost=cost) or f"> ### ${cost}",
        _safe_msg(msg, "system_hero_meta", runs=runs, usage=usage)
        or f"> Runs **{runs}** · usage **{usage}%**",
    ]
    return "\n".join(x for x in lines if x) + "\n"
