from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# (comment)
_INSIGHT_HARD_MAX = 4500


from planning_bot.core.pdmsg import pdmsg
def _sparkline(hours: List[float]) -> str:
    if not hours:
        return ""
    mx = max(hours) or 1.0
    chars = "▁▂▃▄▅▆▇"
    return "".join(
        chars[min(len(chars) - 1, int((h / mx) * (len(chars) - 1) + 0.001))] for h in hours
    )


def _clip_insights(text: str, max_chars: int = _INSIGHT_HARD_MAX) -> str:
    'Operation implementation.'
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    for sep in ("\n\n", "\n", "— ", ". "):
        i = cut.rfind(sep)
        if i > max_chars * 0.55:
            cut = cut[:i].rstrip()
            break
    return cut + pdmsg("auto_9b7b66ce15")


def _mermaid_pie(hours: Dict[str, float], pie_title: str, top: int = 6) -> str:
    items = sorted(hours.items(), key=lambda kv: kv[1], reverse=True)[:top]
    if not items or sum(v for _, v in items) <= 0:
        return ""
    lines = ["```mermaid", "pie showData", f'    title "{pie_title}"']
    for k, v in items:
        lines.append(f'    "{(k or "—")[:36]}" : {v}')
    lines.append("```")
    return "\n".join(lines)


def render_meeting_focus_dashboard(
    generated_at: str,
    analytics: Dict[str, Any],
    insights_md: str,
    *,
    week_wiki: Optional[str] = None,
    life_wiki: Optional[str] = None,
) -> str:
    week_wiki = week_wiki or pdmsg("auto_95e2cc8d19")
    life_wiki = life_wiki or pdmsg("auto_fa4234819c")
    today = date.today()
    days_data: List[Dict] = analytics.get("days") or []
    tot: Dict = analytics.get("totals") or {}
    hrs = [float(d.get("meeting_hours_rounded", 0)) for d in days_data]
    spark = _sparkline(hrs)

    nav = pdmsg("calendar_nav_callout")
    lines: List[str] = [
        pdmsg("auto_c3a0060b1b", _p1=today.strftime('%d.%m.%Y')),
        "",
        *(([nav, ""] if nav.strip() else [])),
        pdmsg("auto_401a7ed2d6", _p1=generated_at, _p3=len(days_data), _p5=tot.get('window_meeting_hours', 0), _p7=tot.get('heavy_days_ge_5h', 0), _p9=spark),
        "",
    ]

    lines += [
        "---",
        "",
        pdmsg("auto_9b872e78bd"),
        "",
    ]
    if week_wiki:
        lines += [f"![[{week_wiki}]]", ""]
    if life_wiki:
        lines += [f"![[{life_wiki}]]", ""]

    ins = _clip_insights(insights_md)
    if ins:
        lines += ["---", "", pdmsg("auto_b517d84574"), "", ins, ""]

    # (comment)
    detail_body: List[str] = [
        pdmsg("auto_a962aee89e"),
        "| :--- | --: | --: | --: | --: | --: |",
    ]
    for d in days_data:
        frag = float(d.get("fragmentation_short_meetings_ratio", 0) or 0)
        ds = ((d.get("date") or "")[5:]).replace("-", ".")
        detail_body.append(
            f"| {d.get('weekday', '')} {ds} "
            f"| {d.get('meeting_hours_rounded', 0)} "
            f"| {d.get('meeting_count', 0)} "
            f"| {d.get('evening_starts_18plus', 0)} "
            f"| {frag * 100:.0f}% "
            f"| {d.get('max_contiguous_busy_minutes', 0)}m |"
        )
    detail_body.append("")
    detail_body.append(pdmsg("auto_01182d875e"))
    detail_body.append("")

    life = analytics.get("life_hours") or {}
    if life:
        detail_body.extend(_mermaid_pie(life, pdmsg("auto_974c1b28ea")).splitlines())
        detail_body.append("")

    rhythms = analytics.get("rhythms") or []
    if rhythms:
        detail_body.append(
            pdmsg("auto_4f3c0a9a48") + " · ".join(f"×{r['count']} {r['title_key'][:40]}" for r in rhythms[:5])
        )

    lines.append(pdmsg("auto_aa763f2047"))
    for ln in detail_body:
        lines.append("> " + ln if ln.strip() else ">")
    lines.append("")
    return "\n".join(lines)


def _update_companion_md(graphics_dir: Path, now_str: str) -> None:
    'Operation implementation.'
    from planning_bot.services.calendar_charts import png_life_filename

    vault = graphics_dir.resolve().parent.parent
    try:
        from shared.chart_paths import chart_path

        life_png = chart_path(vault, "chart_calendar_sections_png")
        week_md = chart_path(vault, "chart_calendar_week_png").with_suffix(".md")
        try:
            life_md = chart_path(vault, "chart_calendar_sections_md")
        except Exception:
            life_md = life_png.with_suffix(".md")
        companions = [week_md, life_md]
    except Exception:
        plan_dir = graphics_dir / "Планирование"
        life_png = plan_dir / png_life_filename()
        companions = [
            plan_dir / pdmsg("auto_f077724de3"),
            plan_dir / pdmsg("auto_6799b4f864"),
        ]

    for p in companions:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        updated = text.replace("{{updated}}", now_str)
        if p.name == pdmsg("auto_6799b4f864") and not life_png.exists():
            updated = re.sub(
                r"!\[[^\]]*\]\([^)]+\)\s*\n*",
                pdmsg("calendar_life_chart_missing_callout"),
                updated,
                count=1,
            )
        updated = re.sub(
            pdmsg("auto_49b159f4e7"),
            pdmsg("calendar_companion_updated", now=now_str),
            updated,
            flags=re.MULTILINE,
        )
        if updated != text:
            p.write_text(updated, encoding="utf-8")


def write_meeting_focus_dashboard(
    path: Path,
    generated_at: str,
    analytics: Dict[str, Any],
    insights_md: str,
) -> None:
    from planning_bot.core.config import GRAPHICS_DIR
    from planning_bot.services.calendar_charts import try_write_calendar_charts

    path.parent.mkdir(parents=True, exist_ok=True)
    week_wiki, life_wiki = try_write_calendar_charts(analytics, GRAPHICS_DIR)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    _update_companion_md(GRAPHICS_DIR, now_str)
    body = render_meeting_focus_dashboard(
        generated_at, analytics, insights_md, week_wiki=week_wiki, life_wiki=life_wiki
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
