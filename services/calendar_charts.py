from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from planning_bot.core.pdmsg import pdmsg
# (comment)
WIKILINK_WEEK = pdmsg("auto_95e2cc8d19")
WIKILINK_LIFE = pdmsg("auto_fa4234819c")
PNG_WEEK = pdmsg("auto_ca23d05890")
PNG_LIFE = pdmsg("auto_10d40715dc")


def try_write_calendar_charts(analytics: Dict[str, Any], graphics_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    'Operation implementation.'
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.debug(pdmsg("auto_59cced6a72"))
        return WIKILINK_WEEK, WIKILINK_LIFE

    graphics_dir.mkdir(parents=True, exist_ok=True)
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
            out = graphics_dir / PNG_WEEK
            fig.savefig(out, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            week_wiki = WIKILINK_WEEK

        life = analytics.get("life_hours") or {}
        items = sorted(life.items(), key=lambda kv: -kv[1])[:8]
        out2 = graphics_dir / PNG_LIFE
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
            fig.savefig(out2, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            life_wiki = WIKILINK_LIFE
        elif out2.exists():
            # (comment)
            out2.unlink()
            logger.info(pdmsg("auto_d0f9e078ba"), out2.name)

    except Exception as e:
        logger.warning(pdmsg("auto_c34d1b44cf"), e)

    return week_wiki, life_wiki
