#!/usr/bin/env python3
"""Build Obsidian dashboard for agent cost / tokens / tools / latency.

Reads logs/agent_traces.jsonl (no message bodies) and writes:
  - vault markdown dashboard (tables + mermaid + optional PNGs)
  - logs/agent_trace_summary.json

Usage:
  PYTHONPATH=. python scripts/build_agent_cost_dashboard.py --days 14
  PYTHONPATH=. python scripts/build_agent_cost_dashboard.py --path logs/agent_traces.jsonl --vault "$VAULT_PATH"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    """Agent root even when LaunchAgent feeds the script via stdin (no real __file__)."""
    import os

    env = (os.environ.get("AGENT_ROOT") or "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return p.resolve()
    try:
        here = Path(__file__)
        if here.is_file():
            return here.resolve().parents[1]
    except Exception:
        pass
    cwd = Path.cwd().resolve()
    if (cwd / "shared").is_dir() and ((cwd / "scripts").is_dir() or (cwd / "planning_bot").is_dir()):
        return cwd
    return cwd


def _default_trace_path() -> Path:
    root = _repo_root()
    return root / "logs" / "agent_traces.jsonl"


def _vault_out_paths(vault: Path) -> tuple[Path, Path, Path, Path]:
    """Resolve dashboard md + chart png paths from vault_paths config.

    Markdown lives under dashboards/charts/… so analytics hub can embed it
    the same way as other analytics notes.
    """
    from shared.chart_paths import chart_path, charts_root

    def _asset(key: str, fallback_rel: str) -> Path:
        try:
            return chart_path(vault, key)
        except Exception:
            return charts_root(vault) / fallback_rel

    md = _asset("agent_cost_dashboard_md", "System/Agent_cost.md")
    tokens_png = _asset("chart_agent_tokens_daily_png", "System/Agent_tokens_daily.png")
    cost_png = _asset("chart_agent_cost_daily_png", "System/Agent_cost_daily.png")
    tools_png = _asset("chart_agent_tools_png", "System/Agent_tools.png")
    return md, tokens_png, cost_png, tools_png


def _try_plot_lines(path: Path, title: str, xs: list[str], ys: list[float], ylabel: str) -> bool:
    if not xs or not ys:
        return False
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(range(len(ys)), ys, marker="o", linewidth=2)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return True


def _try_plot_bars(path: Path, title: str, labels: list[str], values: list[float]) -> bool:
    if not labels:
        return False
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.barh(range(len(labels)), values)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return True


def _wikilink(vault: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(vault.resolve())
        return f"![[{rel.as_posix()}]]"
    except Exception:
        return f"![[{path.name}]]"


def render_markdown(
    summary,
    *,
    vault: Path,
    tokens_png: Path | None,
    cost_png: Path | None,
    tools_png: Path | None,
) -> str:
    from shared.charts.mermaid import mermaid_pie, mermaid_xychart_lines

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    d = summary.as_dict()
    lines: list[str] = [
        "# ✦ Стоимость агента",
        "",
        f"> [!info] Окно — последние **{d['days']}д** · обновлено `{ts}`",
        f"> Прогонов **{d['runs']}** · токенов **{d['total_tokens']:,}** · "
        f"оценка **${d['est_cost_usd']:.4f}** · вызовов инструментов **{d['tool_calls_executed']}**",
        "",
        "## Зачем это",
        "",
        "Прозрачный срез по тратам и эффективности агента: токены, оценка в USD, "
        "вызовы инструментов, размер контекста, латентность. Без тел сообщений — "
        "только операционные метрики из `agent_traces.jsonl`.",
        "",
        "## Снимок",
        "",
        "| Метрика | Значение |",
        "| --- | ---: |",
        f"| Прогонов | {d['runs']} |",
        f"| Токены промпта | {d['prompt_tokens']:,} |",
        f"| Токены ответа | {d['completion_tokens']:,} |",
        f"| Токены всего | {d['total_tokens']:,} |",
        f"| Оценка стоимости (USD) | ${d['est_cost_usd']:.4f} |",
        f"| Стоимость / прогон | ${(d['est_cost_usd'] / d['runs']) if d['runs'] else 0:.5f} |",
        f"| Вызовов инструментов | {d['tool_calls_executed']} |",
        f"| Среднее LLM-раундов / прогон | {d['avg_rounds']:.2f} |",
        f"| Среднее выбранных инструментов | {d['avg_selected_tools']:.1f} |",
        f"| Пик контекста (символы) | {d['avg_context_peak']:.0f} |",
        f"| Латентность p50 / p95 (мс) | {d['p50_latency_ms']:.0f} / {d['p95_latency_ms']:.0f} |",
        f"| Покрытие usage | {d['usage_coverage_pct']:.1f}% |",
        "",
        "## Наблюдения",
        "",
    ]
    for tip in d.get("insights") or []:
        lines.append(f"- {tip}")
    if not d.get("insights"):
        lines.append("- (пока нет)")

    lines.extend(["", "## По дням", ""])
    daily = d.get("daily") or []
    if daily:
        lines.append("| Дата | Прогоны | Токены | Оценка $ | Тулы |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for row in daily[-21:]:
            lines.append(
                f"| {row['date']} | {row['runs']} | {row['tokens']:,} | "
                f"${row['est_cost_usd']:.4f} | {row['tool_calls']} |"
            )
        xs = [r["date"][5:] for r in daily[-14:]]  # MM-DD
        tok = [float(r["tokens"]) for r in daily[-14:]]
        cost = [float(r["est_cost_usd"]) * 10000 for r in daily[-14:]]  # scale for chart
        if len(xs) >= 2:
            lines.extend(
                [
                    "",
                    "```mermaid",
                    mermaid_xychart_lines(
                        xs,
                        {"tokens": tok},
                        "Токены по дням",
                        y_label="токены",
                    ),
                    "```",
                    "",
                    "```mermaid",
                    mermaid_xychart_lines(
                        xs,
                        {"cost_x1e4": cost},
                        "Оценка стоимости (USD ×10000)",
                        y_label="USD*10000",
                    ),
                    "```",
                ]
            )
    else:
        lines.append("_По дням пока нет строк._")

    if tokens_png and tokens_png.is_file():
        lines.extend(["", "### График токенов", "", _wikilink(vault, tokens_png), ""])
    if cost_png and cost_png.is_file():
        lines.extend(["", "### График стоимости", "", _wikilink(vault, cost_png), ""])

    lines.extend(["", "## По доменам", ""])
    dom_cost = d.get("domain_cost") or []
    if dom_cost:
        lines.append("| Домен | Прогоны | Оценка $ |")
        lines.append("| --- | ---: | ---: |")
        for row in dom_cost:
            lines.append(
                f"| {row['domain']} | {row['runs']} | ${row['est_cost_usd']:.4f} |"
            )
        pie = [(r["domain"], float(r["est_cost_usd"]) * 1_000_000) for r in dom_cost]
        if sum(v for _, v in pie) > 0:
            lines.extend(
                [
                    "",
                    "```mermaid",
                    mermaid_pie([(a, max(1.0, b)) for a, b in pie], "Стоимость по доменам"),
                    "```",
                ]
            )
    else:
        lines.append("_Разбивки по доменам пока нет._")

    lines.extend(["", "## Причины завершения", ""])
    reasons = d.get("end_reasons") or {}
    if reasons:
        lines.append("| Причина | Кол-во |")
        lines.append("| --- | ---: |")
        for k, v in reasons.items():
            lines.append(f"| `{k}` | {v} |")
    else:
        lines.append("_н/д_")

    lines.extend(["", "## Топ инструментов", ""])
    top = d.get("top_tools") or []
    if top:
        lines.append("| Инструмент | Вызовы |")
        lines.append("| --- | ---: |")
        for name, n in top:
            lines.append(f"| `{name}` | {n} |")
        if tools_png and tools_png.is_file():
            lines.extend(["", _wikilink(vault, tools_png), ""])
    else:
        lines.append("_Вызовов инструментов пока не записано._")

    lines.extend(
        [
            "",
            "## Как обновить",
            "",
            "```bash",
            "PYTHONPATH=. python scripts/build_agent_cost_dashboard.py --days 14",
            "# или: PYTHONPATH=. python scripts/agent_trace_rollup.py --days 14 --json",
            "```",
            "",
            "Цены: `config/agent/platform.yaml` → `agent_trace.pricing` "
            "(USD за 1M токенов). Трейсы: `AGENT_TRACE=1`.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build agent cost dashboard for Obsidian")
    p.add_argument("--path", type=Path, default=None, help="agent_traces.jsonl")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="Override markdown path")
    p.add_argument("--no-png", action="store_true")
    args = p.parse_args(argv)

    # Ensure repo imports resolve when run as script.
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from shared.agent.trace_analytics import load_trace_rows, summarize_traces
    from shared.paths import vault_root_optional

    trace_path = args.path or _default_trace_path()
    rows = load_trace_rows(trace_path, days=args.days)
    summary = summarize_traces(rows, days=args.days)

    summary_json = root / "logs" / "agent_trace_summary.json"
    try:
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(
            json.dumps(summary.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"warning: could not write {summary_json}: {exc}", file=sys.stderr)

    vault = args.vault or vault_root_optional()
    if vault is None:
        print(f"summary written: {summary_json} (no VAULT_PATH — skip markdown)", file=sys.stderr)
        print(
            f"runs={summary.runs} tokens={summary.total_tokens} "
            f"est_usd={summary.est_cost_usd:.4f}"
        )
        return 0

    vault = vault.resolve()
    md_path, tokens_png, cost_png, tools_png = _vault_out_paths(vault)
    if args.out:
        md_path = args.out

    if not args.no_png and summary.daily:
        xs = [r["date"][5:] for r in summary.daily]
        _try_plot_lines(
            tokens_png,
            "Токены агента / день",
            xs,
            [float(r["tokens"]) for r in summary.daily],
            "токены",
        )
        _try_plot_lines(
            cost_png,
            "Оценка стоимости агента / день (USD)",
            xs,
            [float(r["est_cost_usd"]) for r in summary.daily],
            "USD",
        )
    if not args.no_png and summary.top_tools:
        labels = [n for n, _ in summary.top_tools[:10]]
        vals = [float(v) for _, v in summary.top_tools[:10]]
        _try_plot_bars(tools_png, "Топ вызванных инструментов", labels, vals)

    md = render_markdown(
        summary,
        vault=vault,
        tokens_png=None if args.no_png else tokens_png,
        cost_png=None if args.no_png else cost_png,
        tools_png=None if args.no_png else tools_png,
    )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    print(f"dashboard: {md_path}")
    print(f"summary: {summary_json}")
    print(
        f"runs={summary.runs} tokens={summary.total_tokens} "
        f"est_usd={summary.est_cost_usd:.4f} coverage={summary.as_dict()['usage_coverage_pct']}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
