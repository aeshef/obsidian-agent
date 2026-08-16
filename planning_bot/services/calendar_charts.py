from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from planning_bot.core.pdmsg import pdmsg


def _vault_from_graphics(graphics_dir: Path) -> Path:
    """GRAPHICS_DIR is <vault>/300_…/Графики → vault is two parents up."""
    return graphics_dir.resolve().parent.parent


def _week_png_path(vault: Path) -> Path:
    from shared.chart_paths import chart_path

    return chart_path(vault, "chart_calendar_week_png")


def _life_png_path(vault: Path) -> Path:
    from shared.chart_paths import chart_path

    return chart_path(vault, "chart_calendar_sections_png")


def _wikilink_for(file_key: str) -> str:
    """Path for ![[…]] embeds — under dashboards/charts, without .png."""
    from shared.vault_paths_config import dashboards_sub, folder, vault_file

    rel = vault_file(file_key)
    if rel.lower().endswith(".png"):
        rel = rel[:-4]
    return f"{folder('dashboards')}/{dashboards_sub('charts')}/{rel}"


def _wikilink_week() -> str:
    try:
        return _wikilink_for("chart_calendar_week_png")
    except Exception:
        return pdmsg("auto_95e2cc8d19")


def _wikilink_life() -> str:
    try:
        return _wikilink_for("chart_calendar_sections_png")
    except Exception:
        return pdmsg("auto_fa4234819c")


def png_week_filename() -> str:
    """Locale-resolved chart basename (call at runtime, not import time)."""
    try:
        from shared.vault_paths_config import vault_file

        return Path(vault_file("chart_calendar_week_png")).name
    except Exception:
        return pdmsg("auto_ca23d05890")


def png_life_filename() -> str:
    try:
        from shared.vault_paths_config import vault_file

        return Path(vault_file("chart_calendar_sections_png")).name
    except Exception:
        return pdmsg("auto_10d40715dc")


def try_write_calendar_charts(analytics: Dict[str, Any], graphics_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    """Write meeting charts into vault_paths subfolder (Планирование/), not Графики/ root."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.debug(pdmsg("auto_59cced6a72"))
        return _wikilink_week(), _wikilink_life()

    vault = _vault_from_graphics(graphics_dir)
    try:
        week_out = _week_png_path(vault)
        life_out = _life_png_path(vault)
    except Exception as e:
        logger.warning("calendar charts: vault_paths fallback to graphics_dir (%s)", e)
        week_out = graphics_dir / png_week_filename()
        life_out = graphics_dir / png_life_filename()

    week_wiki: Optional[str] = None
    life_wiki: Optional[str] = None

    try:
        days: List[Dict] = analytics.get("days") or []
        if days:
            labels = []
            vals = []
            for d in days:
                wd = d.get("weekday", "")
                ds = (d.get("date") or "")[5:]
                labels.append(f"{wd} {ds}")
                vals.append(float(d.get("meeting_hours_rounded", 0)))

            fig, ax = plt.subplots(figsize=(7.2, 3.0), dpi=130)
            y = list(range(len(labels)))
            ax.barh(y, vals, color="#3d7ea6", height=0.72, edgecolor="white", linewidth=0.5)
            ax.set_yticks(y)
            ax.set_yticklabels(labels, fontsize=9)
            ax.set_xlabel(pdmsg("auto_644f4feb02"), fontsize=9)
            ax.set_title(pdmsg("auto_1cf2476692"), fontsize=11, fontweight="bold", pad=8)
            ax.grid(axis="x", alpha=0.35, linestyle="--")
            ax.set_axisbelow(True)
            fig.tight_layout()
            week_out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(week_out, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            week_wiki = _wikilink_week()

        life = analytics.get("life_hours") or {}
        items = sorted(life.items(), key=lambda kv: -kv[1])[:8]
        if items:
            names = [(k[:24] if k else "—") for k, _ in items]
            hours = [v for _, v in items]

            fig, ax = plt.subplots(figsize=(5.8, 2.8), dpi=130)
            y = list(range(len(names)))
            ax.barh(y, hours, color="#5a9a5e", height=0.62, edgecolor="white", linewidth=0.5)
            ax.set_yticks(y)
            ax.set_yticklabels(names, fontsize=9)
            ax.set_xlabel(pdmsg("auto_aa0b458eec"), fontsize=9)
            ax.set_title(pdmsg("auto_5777c551af"), fontsize=11, fontweight="bold", pad=8)
            ax.grid(axis="x", alpha=0.35, linestyle="--")
            ax.set_axisbelow(True)
            fig.tight_layout()
            life_out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(life_out, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            life_wiki = _wikilink_life()
        elif life_out.exists():
            life_out.unlink()
            logger.info(pdmsg("auto_d0f9e078ba"), life_out.name)

    except Exception as e:
        logger.warning(pdmsg("auto_c34d1b44cf"), e)

    return week_wiki, life_wiki
