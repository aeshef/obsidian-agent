#!/usr/bin/env python3
from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / pdmsg("auto_0785c86cb9")).is_dir() and (p / pdmsg("auto_1c7277d3a5")).is_dir():
            return p
    return start.parents[3]


def _kcal_from_grams(
    p: float | None, f: float | None, c: float | None
) -> tuple[float, float, float]:
    'Operation implementation.'
    P = max(0.0, 4.0 * float(p or 0))
    F_ = max(0.0, 9.0 * float(f or 0))
    C = max(0.0, 4.0 * float(c or 0))
    return (P, F_, C)


def _pick_per_day(
    snapshots: list[dict],
) -> list[tuple[str, float, float, float, str, float, float, float]]:
    'Operation implementation.'
    by_day: dict[str, dict] = {}
    for s in sorted(snapshots, key=lambda x: str(x.get("ts", ""))):
        ts = str(s.get("ts", ""))[:10]
        if not ts or len(ts) < 10:
            continue
        p = s.get("proteins_g")
        f_ = s.get("fats_g")
        c = s.get("carbs_g")
        if p is None and f_ is None and c is None:
            continue
        pk, fk, ck = _kcal_from_grams(
            p if p is not None else 0, f_ if f_ is not None else 0, c if c is not None else 0
        )
        if pk + fk + ck < 0.1:
            continue
        by_day[ts] = s

    rows: list[tuple[str, float, float, float, str, float, float, float]] = []
    for d in sorted(by_day.keys()):
        s = by_day[d]
        pk, fk, ck = _kcal_from_grams(
            s.get("proteins_g"), s.get("fats_g"), s.get("carbs_g")
        )
        pg = float(s.get("proteins_g") or 0)
        fg = float(s.get("fats_g") or 0)
        cg = float(s.get("carbs_g") or 0)
        dt = datetime.fromisoformat(d)
        label = dt.strftime("%d.%m")
        rows.append((d, pk, fk, ck, label, pg, fg, cg))
    return rows


def _last_numeric_by_day(
    snapshots: list[dict], key: str
) -> dict[str, float]:
    'Operation implementation.'
    out: dict[str, float] = {}
    for s in sorted(snapshots, key=lambda x: str(x.get("ts", ""))):
        day = str(s.get("ts", ""))[:10]
        if len(day) < 10:
            continue
        v = s.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:  # NaN
            continue
        out[day] = f
    return out


def _line_series(
    kcal_dates: list[str], weight_by_day: dict[str, float], steps_by_day: dict[str, float]
) -> tuple[list[float], list[float]]:
    'Operation implementation.'
    w_vals: list[float] = []
    s_vals: list[float] = []
    for dstr in kcal_dates:
        d0 = date.fromisoformat(dstr)
        wday = (d0 + timedelta(days=1)).isoformat()
        wv = weight_by_day.get(wday)
        w_vals.append(wv if wv is not None else float("nan"))
        sv = steps_by_day.get(dstr)
        s_vals.append(sv if sv is not None else float("nan"))
    return w_vals, s_vals


def _fat_pct_series(kcal_dates: list[str], fat_by_day: dict[str, float]) -> list[float]:
    'Operation implementation.'
    out: list[float] = []
    for dstr in kcal_dates:
        d0 = date.fromisoformat(dstr)
        wday = (d0 + timedelta(days=1)).isoformat()
        fp = fat_by_day.get(wday)
        out.append(fp if fp is not None else float("nan"))
    return out


def _macro_table_md(
    rows: list[tuple[str, float, float, float, str, float, float, float]],
    fat_vals: list[float],
) -> str:
    'Operation implementation.'
    import math

    lines = [
        pdmsg("auto_bc733d7c17"),
        "|------|-----:|-----:|-----:|-----:|-------:|",
    ]
    for i, r in enumerate(rows):
        d, pk, fk, ck, lbl, pg, fg, cg = r
        kcal = pk + fk + ck
        fp = fat_vals[i] if i < len(fat_vals) else float("nan")
        fp_s = f"{fp:.1f}" if isinstance(fp, (int, float)) and math.isfinite(fp) else "—"
        lines.append(
            f"| {lbl} | {kcal:.0f} | {pg:.0f} | {fg:.0f} | {cg:.0f} | {fp_s} |"
        )
    return "\n".join(lines) + "\n"


def _write_out(
    rows: list[tuple[str, float, float, float, str, float, float, float]],
    w_line: list[float] | None,
    s_line: list[float] | None,
    graphics: Path,
    dash: Path,
    ts: str,
    fat_by_day: dict[str, float],
) -> None:
    graphics.mkdir(parents=True, exist_ok=True)
    comp_md = graphics / pdmsg("auto_443f6eab29")
    if not rows:
        comp_md.write_text(
            pdmsg("auto_eae7dbddcc", _p1=ts),
            encoding="utf-8",
        )
        md_body = pdmsg("auto_3199a9f58d", _p1=ts)
        dash.write_text(md_body, encoding="utf-8")
        return

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        comp_md.write_text(
            pdmsg("auto_737bdc69e5", _p1=ts),
            encoding="utf-8",
        )
        return

    w_line = w_line or [float("nan")] * len(rows)
    s_line = s_line or [float("nan")] * len(rows)

    labels = [r[4] for r in rows]
    p_kc = [r[1] for r in rows]
    f_kc = [r[2] for r in rows]
    c_kc = [r[3] for r in rows]
    n = len(labels)
    x = np.arange(n, dtype=float)
    width = min(0.7, max(0.08, 12.0 / n)) if n else 0.5
    c_arr = np.array(c_kc, dtype=float)
    f_arr = np.array(f_kc, dtype=float)
    p_arr = np.array(p_kc, dtype=float)
    w_arr = np.array(w_line[:n], dtype=float) if w_line else np.full(n, float("nan"))
    s_arr = np.array(s_line[:n], dtype=float) if s_line else np.full(n, float("nan"))

    fat_pct_line = _fat_pct_series([r[0] for r in rows], fat_by_day)

    fig_w = max(8.0, min(n * 0.48, 48.0))
    fig, ax1 = plt.subplots(figsize=(fig_w, 6.4), dpi=144)

    tot_arr = c_arr + f_arr + p_arr
    y_top = float(np.nanmax(tot_arr)) if np.isfinite(tot_arr).any() else 1.0
    ax1.set_ylim(0, y_top * 1.14)

    # (comment)
    bar_kw = dict(edgecolor="white", linewidth=0.6, zorder=2, alpha=0.94)
    b1 = ax1.bar(x, p_arr, width, label=pdmsg("auto_9a07a218df"), color="#43a047", **bar_kw)
    b2 = ax1.bar(x, f_arr, width, bottom=p_arr, label=pdmsg("auto_89b569b67a"), color="#fb8c00", **bar_kw)
    b3 = ax1.bar(
        x, c_arr, width, bottom=p_arr + f_arr, label=pdmsg("auto_a605043d53"), color="#1e88e5", **bar_kw
    )

    tick_step = 2 if n > 22 else 1
    tick_x = x[::tick_step]
    tick_lbl = labels[::tick_step]
    ax1.set_xticks(tick_x)
    rot = 45 if n > 8 else 0
    ax1.set_xticklabels(
        tick_lbl,
        rotation=rot,
        ha="right" if rot else "center",
        fontsize=8,
    )
    ax1.tick_params(axis="x", pad=6 if rot else 3)
    ax1.set_ylabel(pdmsg("auto_34b1e2b3f5"), fontsize=10, color="#1a1a1a")
    ax1.set_title(pdmsg("auto_afd5098f44"), fontsize=11, fontweight="bold", pad=6)
    ax1.grid(axis="y", alpha=0.22, linestyle="--", linewidth=0.5, zorder=0)
    ax1.set_axisbelow(True)
    ax1.tick_params(axis="y", labelsize=8)

    COL_W = "#c62828"
    COL_S = "#311b92"
    from matplotlib import patheffects as pe

    line_halo = [pe.withStroke(linewidth=4.5, foreground="#ffffff", alpha=0.98), pe.Normal()]
    show_markers = n <= 18
    lw, ls_ = None, None
    ax2, ax3 = None, None

    if np.isfinite(w_arr).any():
        ax2 = ax1.twinx()
        (lw,) = ax2.plot(
            x,
            w_arr,
            linestyle="-",
            marker="o" if show_markers else None,
            color=COL_W,
            linewidth=2.8,
            markersize=6 if show_markers else 0,
            markeredgewidth=1.5,
            markeredgecolor="#ffffff",
            markerfacecolor=COL_W,
            label=pdmsg("auto_e9e498371d"),
            zorder=5,
        )
        lw.set_path_effects(line_halo)
        ax2.set_ylabel(pdmsg("auto_84521de53b"), fontsize=9, color=COL_W, fontweight="bold", labelpad=4)
        ax2.tick_params(axis="y", labelsize=8, labelcolor=COL_W)
        ax2.spines["right"].set_color(COL_W)
        ax2.spines["right"].set_linewidth(1.5)

    if np.isfinite(s_arr).any():
        ax3 = ax1.twinx()
        if ax2 is not None:
            ax3.spines["right"].set_position(("outward", 54))
        (ls_,) = ax3.plot(
            x,
            s_arr,
            linestyle=(0, (8, 4)),
            marker="D" if show_markers else None,
            color=COL_S,
            linewidth=2.6,
            markersize=5 if show_markers else 0,
            markeredgewidth=1.2,
            markeredgecolor="#ffffff",
            markerfacecolor=COL_S,
            label=pdmsg("auto_640721bf8d"),
            zorder=4,
        )
        ls_.set_path_effects(line_halo)
        ax3.set_ylabel(pdmsg("auto_7e0aa97634"), fontsize=9, color=COL_S, fontweight="bold", labelpad=2)
        ax3.tick_params(axis="y", labelsize=8, labelcolor=COL_S)
        ax3.spines["right"].set_color(COL_S)
        ax3.spines["right"].set_linewidth(1.5)

    kcal_fs = 7 if n > 20 else 8
    for i, xi in enumerate(x):
        t = float(tot_arr[i])
        if t > 0:
            ax1.text(
                xi,
                t + y_top * 0.012,
                f"{t:.0f}",
                ha="center",
                va="bottom",
                fontsize=kcal_fs,
                fontweight="bold",
                color="#424242",
                clip_on=True,
                zorder=3,
            )

    h_b = [b1, b2, b3]
    bar_lbls = [pdmsg("auto_9a07a218df"), pdmsg("auto_89b569b67a"), pdmsg("auto_a605043d53")]
    handles = list(h_b)
    hlabels = list(bar_lbls)
    if lw is not None:
        handles.append(lw)
        hlabels.append(lw.get_label())
    if ls_ is not None:
        handles.append(ls_)
        hlabels.append(ls_.get_label())
    fig.legend(
        handles,
        hlabels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.01),
        ncol=min(5, len(handles)),
        fontsize=8,
        frameon=True,
        framealpha=0.95,
    )
    fig.subplots_adjust(left=0.07, right=0.90, bottom=0.16, top=0.94)
    png = graphics / pdmsg("auto_e05b321307")
    fig.savefig(png, bbox_inches="tight", facecolor="white", pad_inches=0.22, dpi=144)
    plt.close(fig)

    table_md = _macro_table_md(rows, fat_pct_line)
    comp_md.write_text(
        pdmsg("auto_aeb265d6f5", _p1=table_md, _p3=ts),
        encoding="utf-8",
    )
    body = pdmsg("auto_c01ff6fe9b", _p1=table_md, _p3=ts)
    dash.write_text(body, encoding="utf-8")
    print(f"OK: {png}, {comp_md}, {dash}")


def main() -> int:
    # (comment)
    os.environ.pop("PYTHONPATH", None)
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=str, help=pdmsg("auto_13eed18124"))
    args = ap.parse_args()
    start = Path(__file__).resolve()
    vault = Path(args.vault).resolve() if args.vault else _discover_vault(start)
    iphone_dir = vault / pdmsg("auto_1c7277d3a5") / pdmsg("auto_145f378b1a") / pdmsg("auto_fb3df31bf5") / "IPhone"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    snapshots: list[dict] = []
    try:
        agent_root = vault / pdmsg("auto_e7eb0224f4") / "Agent"
        if str(agent_root) not in sys.path:
            sys.path.insert(0, str(agent_root))
        from planning_bot.services.iphone_context_parser import get_snapshots

        snapshots = get_snapshots(iphone_dir, days=None)
    except Exception as e:
        print(f"WARN: get_snapshots failed ({e}), fallback iphone_week.json", file=sys.stderr)
        week_json = vault / pdmsg("auto_1c7277d3a5") / pdmsg("auto_145f378b1a") / pdmsg("auto_fb3df31bf5") / "iphone_week.json"
        if week_json.is_file():
            snapshots = json.loads(week_json.read_text(encoding="utf-8")).get("snapshots") or []

    if not snapshots and not iphone_dir.is_dir():
        g = vault / pdmsg("auto_1c7277d3a5") / pdmsg("auto_1f4101e6f4")
        d = vault / pdmsg("auto_1c7277d3a5") / pdmsg("auto_a9e6f3071c")
        g.mkdir(parents=True, exist_ok=True)
        (g / pdmsg("auto_443f6eab29")).write_text(
            pdmsg("auto_a76864c8ac", _p1=ts),
            encoding="utf-8",
        )
        d.write_text(
            pdmsg("auto_daa59085ad", _p1=iphone_dir),
            encoding="utf-8",
        )
        return 0
    rows = _pick_per_day(snapshots)
    body_on = os.environ.get("CAP_FEATURE_HEALTH_BODY_METRICS", "1") == "1"
    w_by = _last_numeric_by_day(snapshots, "weight_kg") if body_on else {}
    s_by = _last_numeric_by_day(snapshots, "steps") if body_on else {}
    fat_by = _last_numeric_by_day(snapshots, "fat_pct") if body_on else {}
    d_list = [r[0] for r in rows]
    w_se, s_se = _line_series(d_list, w_by, s_by)
    _write_out(
        rows,
        w_se,
        s_se,
        vault / pdmsg("auto_1c7277d3a5") / pdmsg("auto_1f4101e6f4"),
        vault / pdmsg("auto_1c7277d3a5") / pdmsg("auto_a9e6f3071c"),
        ts,
        fat_by,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
