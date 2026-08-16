from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from planning_bot.core.pdmsg import pdmsg

_INSIGHT_HARD_MAX = 4500


def _fmt_hours(h: float) -> str:
    """Drop trailing .0 for hero/mix readability."""
    try:
        x = float(h)
    except (TypeError, ValueError):
        return str(h)
    if abs(x - round(x)) < 1e-6:
        return str(int(round(x)))
    return f"{x:.1f}"


def _sep(key: str, fallback: str = "·") -> str:
    """Join separator; dmsg strips edges, so pad a glyph for readable lists."""
    core = (pdmsg(key) or "").strip() or fallback
    return f" {core} "


def _mix_bits(activity: Dict[str, float], *, limit: int = 5) -> str:
    sep = _sep("calendar_dash_mix_join")
    parts = []
    for name, hrs in sorted(activity.items(), key=lambda kv: -float(kv[1] or 0))[:limit]:
        parts.append(pdmsg("calendar_dash_mix_item", name=name, hours=_fmt_hours(hrs)))
    return sep.join(parts)


def _callout(kind: str, title: str, *body: str) -> List[str]:
    lines = [f"> [!{kind}] {title}"]
    for b in body:
        lines.append(f"> {b}" if b else ">")
    lines.append("")
    return lines


def render_meeting_focus_dashboard(
    generated_at: str,
    analytics: Dict[str, Any],
    insights_md: str = "",
    *,
    week_wiki: Optional[str] = None,
    life_wiki: Optional[str] = None,
) -> str:
    """Meetings dashboard: hero + next 48h + free windows + charts. No rhythm spam."""
    _ = insights_md
    _ = generated_at
    week_wiki = week_wiki or pdmsg("auto_95e2cc8d19")
    life_wiki = life_wiki or pdmsg("auto_fa4234819c")
    today = date.today()
    days_data: List[Dict] = analytics.get("days") or []
    tot: Dict = analytics.get("totals") or {}
    invite = float(tot.get("invite_hours", tot.get("window_meeting_hours", 0)) or 0)

    activity = analytics.get("activity_hours") or analytics.get("life_hours") or {}
    peak = next((d for d in days_data if d.get("date") == tot.get("peak_day")), None)
    pressure = analytics.get("top_pressure") or []
    peak_title = (pressure[0].get("title") or "")[:40] if pressure else ""
    typed_share = float(analytics.get("typed_share") or 0)

    nav = pdmsg("calendar_nav_callout")
    lines: List[str] = [
        pdmsg("calendar_dash_title", date=today.strftime("%d.%m.%Y")),
        "",
        *(([nav, ""] if nav.strip() else [])),
        pdmsg("calendar_dash_hero_open"),
        pdmsg("calendar_dash_hero_hours", hours=_fmt_hours(invite)),
    ]
    mix = _mix_bits(activity) if typed_share >= 0.15 else ""
    if mix:
        lines.append(pdmsg("calendar_dash_hero_mix", mix=mix))
    elif invite > 0 and typed_share < 0.15:
        tip = pdmsg("calendar_dash_hero_untyped", default="")
        if tip:
            lines.append(tip)
    if peak and float(peak.get("meeting_hours_rounded") or 0) > 0:
        lines.append(
            pdmsg(
                "calendar_dash_hero_peak",
                weekday=peak.get("weekday"),
                date=str(peak.get("date") or "")[5:],
                hours=_fmt_hours(peak.get("meeting_hours_rounded")),
                title=peak_title,
            )
        )
    lines += [
        pdmsg("calendar_dash_hero_updated", date=today.strftime("%d.%m.%Y")),
        "",
    ]

    upcoming = analytics.get("upcoming") or []
    if upcoming:
        up_body: List[str] = [
            "### "
            + pdmsg(
                "calendar_dash_upcoming_head",
                n=len(upcoming),
                default=f"**{len(upcoming)}** slots",
            ),
            "",
        ]
        for u in upcoming[:12]:
            when = pdmsg(
                "calendar_dash_upcoming_when",
                weekday=u.get("weekday"),
                date=str(u.get("date") or "")[5:],
                start=u.get("start"),
                end=u.get("end"),
                default=f"{u.get('weekday')} {str(u.get('date') or '')[5:]} {u.get('start')}–{u.get('end')}",
            )
            up_body.append(
                pdmsg(
                    "calendar_dash_upcoming_line",
                    when=when,
                    title=(u.get("title") or "")[:70],
                    default=f"- **{when}** · {(u.get('title') or '')[:70]}",
                )
            )
        lines.extend(
            _callout(
                "abstract",
                pdmsg("calendar_dash_upcoming_title", default="Today / tomorrow"),
                *up_body,
            )
        )
    else:
        lines.extend(
            _callout(
                "success",
                pdmsg("calendar_dash_upcoming_title", default="Today / tomorrow"),
                pdmsg("calendar_dash_upcoming_empty", default="No timed slots in the next 48h."),
            )
        )

    free = analytics.get("free_windows") or []
    if free:
        free_body: List[str] = [
            pdmsg(
                "calendar_dash_free_note",
                default="Weekday gaps ≥1.5h between 09:00–18:00 — deep-work candidates.",
            ),
            "",
        ]
        for w in free[:8]:
            free_body.append(
                pdmsg(
                    "calendar_dash_free_line",
                    weekday=w.get("weekday"),
                    date=str(w.get("date") or "")[5:],
                    start=w.get("start"),
                    end=w.get("end"),
                    hours=_fmt_hours(w.get("hours")),
                    default=(
                        f"- **{w.get('weekday')} {str(w.get('date') or '')[5:]}** "
                        f"· {w.get('start')}–{w.get('end')} ({_fmt_hours(w.get('hours'))} h)"
                    ),
                )
            )
        lines.extend(
            _callout(
                "success",
                pdmsg("calendar_dash_free_title", default="Free windows"),
                *free_body,
            )
        )

    markers = analytics.get("day_markers") or []
    if markers:
        mark_body: List[str] = [
            pdmsg(
                "calendar_dash_markers_note",
                default="All-day / block labels — life context, not meeting load.",
            ),
            "",
        ]
        for m in markers[:8]:
            mark_body.append(
                pdmsg(
                    "calendar_dash_markers_line",
                    weekday=m.get("weekday"),
                    date=str(m.get("date") or "")[5:],
                    title=(m.get("title") or "")[:70],
                    default=f"- **{m.get('weekday')} {str(m.get('date') or '')[5:]}** · {(m.get('title') or '')[:70]}",
                )
            )
        lines.extend(
            _callout(
                "note",
                pdmsg("calendar_dash_markers_title", default="Day markers"),
                *mark_body,
            )
        )

    heavy = analytics.get("heavy_days") or []
    if heavy:
        bits = _sep("calendar_dash_mix_join").join(
            pdmsg(
                "calendar_dash_heavy_item",
                weekday=h.get("weekday"),
                date=str(h.get("date") or "")[5:],
                hours=_fmt_hours(h.get("hours")),
                default=f"{h.get('weekday')} {str(h.get('date') or '')[5:]} {_fmt_hours(h.get('hours'))}h",
            )
            for h in heavy[:5]
        )
        lines.extend(
            _callout(
                "warning" if len(heavy) >= 3 else "abstract",
                pdmsg("calendar_dash_heavy_title", default="Heavy days (≥3h)"),
                bits,
            )
        )

    show_types = typed_share >= 0.15 and bool(life_wiki)
    if week_wiki or show_types:
        lines += [pdmsg("calendar_dash_section_load"), ""]
        if week_wiki:
            lines += [f"![[{week_wiki}]]", ""]
        if show_types:
            lines += [f"![[{life_wiki}]]", ""]
    if pressure:
        lines.append(
            "> [!note]- " + pdmsg("calendar_dash_section_pressure_fold", default="Large slots (week)")
        )
        for p in pressure:
            lines.append(
                "> "
                + pdmsg(
                    "calendar_dash_pressure_fold_line",
                    weekday=p.get("weekday"),
                    date=str(p.get("date") or "")[5:],
                    hours=_fmt_hours(p.get("hours")),
                    title=(p.get("title") or "")[:70],
                    default=(
                        f"- **{p.get('weekday')} {str(p.get('date') or '')[5:]}** "
                        f"· {_fmt_hours(p.get('hours'))} h · {(p.get('title') or '')[:70]}"
                    ),
                )
            )
        lines.append("")

    unclassified = analytics.get("unclassified_top") or []
    if unclassified and typed_share >= 0.15:
        lines.append(
            "> [!note]- "
            + pdmsg("calendar_dash_section_unclassified_fold", default="Still untyped")
        )
        for u in unclassified[:5]:
            lines.append(
                "> "
                + pdmsg(
                    "calendar_dash_unclassified_fold_line",
                    hours=u.get("hours"),
                    title=(u.get("title") or "")[:70],
                    default=f"- {u.get('hours')} h · {(u.get('title') or '')[:70]}",
                )
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _companion_targets(graphics_dir: Path) -> list[tuple[Path, str, str, Path]]:
    vault = graphics_dir.resolve().parent.parent
    try:
        from shared.chart_paths import chart_path

        week_png = chart_path(vault, "chart_calendar_week_png")
        life_png = chart_path(vault, "chart_calendar_sections_png")
        try:
            life_md = chart_path(vault, "chart_calendar_sections_md")
        except Exception:
            life_md = life_png.with_suffix(".md")
        return [
            (week_png.with_suffix(".md"), "calendar_companion_week_body", week_png.name, week_png),
            (life_md, "calendar_companion_activity_body", life_png.name, life_png),
        ]
    except Exception:
        from planning_bot.services.calendar_charts import png_life_filename, png_week_filename

        try:
            from shared.vault_paths_config import planning_sub

            plan_name = planning_sub("graphs_planning")
        except Exception:
            plan_name = "Planning"
        plan_dir = graphics_dir / str(plan_name)
        week_name = png_week_filename()
        life_name = png_life_filename()
        week_png = plan_dir / week_name
        life_png = plan_dir / life_name
        return [
            (week_png.with_suffix(".md"), "calendar_companion_week_body", week_name, week_png),
            (life_png.with_suffix(".md"), "calendar_companion_activity_body", life_name, life_png),
        ]


def _update_companion_md(graphics_dir: Path, now_str: str) -> None:
    for md_path, body_key, png_name, png_path in _companion_targets(graphics_dir):
        body = pdmsg(body_key, png_name=png_name, now=now_str).strip()
        if not body:
            if not md_path.exists():
                continue
            text = md_path.read_text(encoding="utf-8")
            updated = text.replace("{{updated}}", now_str)
            updated = re.sub(
                pdmsg("auto_49b159f4e7"),
                pdmsg("calendar_companion_updated", now=now_str),
                updated,
                flags=re.MULTILINE,
            )
            if updated != text:
                md_path.write_text(updated, encoding="utf-8")
            continue
        if body_key == "calendar_companion_activity_body" and not png_path.exists():
            body = re.sub(
                r"!\[[^\]]*\]\([^)]+\)\s*\n*",
                pdmsg("calendar_life_chart_missing_callout"),
                body,
                count=1,
            )
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(body.rstrip() + "\n", encoding="utf-8")


def write_meeting_focus_dashboard(
    path: Path,
    generated_at: str,
    analytics: Dict[str, Any],
    insights_md: str = "",
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
