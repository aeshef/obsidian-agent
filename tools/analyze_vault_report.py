#!/usr/bin/env python3
"""
Запускает оба анализа (теги + дубли) и при необходимости пишет сводный отчёт в файл.
Хранилище не меняет — только чтение. Отчёт можно писать в 300_Дашборды или в папку скриптов.

  python analyze_vault_report.py
  python analyze_vault_report.py --out "300_Дашборды/Аудит_хранилища_отчет.md"
  PYTHONPATH=../.. python tools/analyze_vault_report.py --vault /path/to/vault --out ...
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
# 800_Автоматизация/Agent — для import knowledge_bot и дочерних подпроцессов
AGENT_DIR = SCRIPT_DIR.parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))


def _vault_root(args: argparse.Namespace) -> Path:
    if args.vault:
        return Path(args.vault).expanduser().resolve()
    from knowledge_bot.core.config import load_config

    return load_config().vault_path


def _parse_last_maintenance_run(log_path: Path) -> dict | None:
    """
    Читает лог vault_write_maintenance.log и возвращает последний полный JSON-блок
    с результатами прогона ({"sync_dir": ..., "steps": [...], "ok": ...}).
    Возвращает None если лог не найден или JSON не распарсился.
    """
    import json as _json

    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    if not text.strip():
        return None

    # Нельзя считать скобки по символам: в JSON внутри stdout_tail/stderr_tail шагов
    # попадают фрагменты вывода с «левыми» { } — тогда последний блок не находится.
    decoder = _json.JSONDecoder()
    last_block: dict | None = None
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        if text[i] != "{":
            i += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, i)
            if isinstance(obj, dict) and "steps" in obj:
                last_block = obj
            i = end
        except ValueError:
            i += 1
    return last_block


def _format_maintenance_run(run: dict) -> list[str]:
    """Форматирует результаты прогона vault_daily_maintenance в читаемые строки."""
    lines: list[str] = []
    if run.get("skipped"):
        reason = run.get("reason", "?")
        extra = ""
        if run.get("wrote_marker"):
            extra = " (маркер дня записан без шагов)"
        lines.append(
            f"**Итоги последнего прогона**: ⏭ **пропуск** — `{reason}`{extra}. "
            "Повторный запуск в тот же день шаги не выполняет — это ожидаемо."
        )
        lines.append("")
        return lines

    ok = run.get("ok", True)
    steps = run.get("steps") or []
    lines.append(f"**Итоги последнего прогона** ({'✅ ok' if ok else '❌ ошибка'}), {len(steps)} шагов:")
    lines.append("")
    step_labels = {
        "sync_hubs": "Хабы (sync_hubs)",
        "apply_wikilinks_batch": "Wikilinks (apply_wikilinks_batch)",
        "retag_notes": "Перетегирование (retag_notes)",
        "reprocess_notes": "Переобработка имён (reprocess_notes)",
    }
    for s in steps:
        name = s.get("name", "?")
        rc = s.get("returncode", "?")
        sec = s.get("seconds", 0)
        label = step_labels.get(name, name)
        status = "✅" if rc == 0 else "❌"
        lines.append(f"  - {status} **{label}** — {sec:.1f}с")
        stdout = (s.get("stdout_tail") or "").strip()
        if stdout:
            # Берём последние 3 строки вывода — самое важное (итог шага)
            tail = [ln for ln in stdout.splitlines() if ln.strip()][-3:]
            for ln in tail:
                lines.append(f"    > {ln}")
        stderr = (s.get("stderr_tail") or "").strip()
        if stderr:
            err_lines = [ln for ln in stderr.splitlines() if ln.strip() and "NOT available" not in ln]
            for ln in err_lines[-2:]:
                lines.append(f"    ⚠ {ln}")
    return lines


def _build_maintenance_section(vault: Path) -> str:
    """Собирает секцию состояния ежедневного обслуживания."""
    import datetime

    from knowledge_bot.services.reprocess_candidates import discover_candidate_paths, load_reprocess_yaml

    lines = ["## 3. Ежедневное обслуживание (vault_daily_maintenance)", ""]

    # Статус хабов
    hubs_dir = vault / "700_База_Данных" / "_Хабы"
    if hubs_dir.exists():
        hubs = sorted(hubs_dir.glob("*.md"))
        lines.append(f"**Хабы** (`700_База_Данных/_Хабы/`): {len(hubs)} файлов")
        for h in hubs:
            mtime = datetime.datetime.fromtimestamp(h.stat().st_mtime).strftime("%Y-%m-%d")
            try:
                text = h.read_text(encoding="utf-8", errors="ignore")
                link_count = text.count("[[")
                lines.append(f"  - `{h.name}` — {link_count} ссылок (обновлён {mtime})")
            except Exception:
                lines.append(f"  - `{h.name}` (обновлён {mtime})")
    else:
        lines.append("**Хабы**: папка `_Хабы/` ещё не создана (запусти `sync_hubs.py --apply`)")

    lines.append("")

    import yaml

    # Tag ontology mappings count
    tag_cfg_path = Path(__file__).resolve().parent.parent / "config" / "tag_ontology.yaml"
    if tag_cfg_path.exists():
        try:
            tcfg = yaml.safe_load(tag_cfg_path.read_text(encoding="utf-8")) or {}
            mappings = tcfg.get("mappings", {}) or {}
            lines.append(f"**Онтология тегов**: {len(mappings)} активных маппингов в `config/tag_ontology.yaml`")
        except Exception:
            lines.append("**Онтология тегов**: ошибка чтения конфига")
    else:
        lines.append("**Онтология тегов**: конфиг не найден")

    lines.append("")

    # Marker file (last run date)
    sync_dir = vault / ".sync"
    marker = sync_dir / "daily_vault_write_maintenance_date.txt"
    if marker.exists():
        last_run = marker.read_text(encoding="utf-8").strip()
        lines.append(f"**Последний запуск обслуживания**: `{last_run}`")
    else:
        lines.append("**Последний запуск обслуживания**: ещё не запускалось (маркер не найден)")

    lines.append("")

    # Итоги последнего прогона: сначала sidecar (пишет runner после каждого полного прогона),
    # иначе разбор лога (obsidian_sync пишет JSON в planning_bot/logs/…; tail может обрезать начало).
    import json as _json

    last_run_data: dict | None = None
    sidecar = sync_dir / "last_vault_maintenance_run.json"
    if sidecar.exists():
        try:
            raw = _json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "steps" in raw:
                last_run_data = raw
        except Exception:
            last_run_data = None

    if last_run_data is None:
        log_candidates = [
            vault / "800_Автоматизация" / "Agent" / "planning_bot" / "logs" / "vault_write_maintenance.log",
            Path(__file__).resolve().parent.parent.parent / "planning_bot" / "logs" / "vault_write_maintenance.log",
        ]
        for lp in log_candidates:
            last_run_data = _parse_last_maintenance_run(lp)
            if last_run_data:
                break

    if last_run_data:
        lines.extend(_format_maintenance_run(last_run_data))
    else:
        lines.append(
            "**Итоги прогона**: нет данных — ни `.sync/last_vault_maintenance_run.json`, "
            "ни распарсиваемого JSON в `planning_bot/logs/vault_write_maintenance.log` "
            "(после следующего успешного 5b.2 появится sidecar)."
        )

    lines.append("")

    # Заметки под reprocess — те же правила, что tools/reprocess_notes.py (config/reprocess.yaml).
    # Путь к конфигу от файла пакета — не зависит от VAULT_PATH / --vault.
    agent_config_dir = Path(__file__).resolve().parent.parent / "config"
    rpcfg = load_reprocess_yaml(agent_config_dir)
    all_generic = discover_candidate_paths(vault, rpcfg, skip_if_flag=False)
    eligible = discover_candidate_paths(vault, rpcfg, skip_if_flag=True)
    skipped_ct = len(all_generic) - len(eligible)
    if all_generic:
        lines.append(
            f"**Заметки для reprocess** (`bad_stem_pattern` из `config/reprocess.yaml`): "
            f"всего **{len(all_generic)}**, в очереди без `reprocess_skip` — **{len(eligible)}**"
            + (f" (с флагом пропуска: {skipped_ct})" if skipped_ct else "")
        )
        for p in eligible[:8]:
            lines.append(f"  - `{p.relative_to(vault)}`")
        if len(eligible) > 8:
            lines.append(f"  - … и ещё {len(eligible) - 8} в очереди")
        if skipped_ct and not eligible:
            lines.append("  - Очередь пуста: все совпадения помечены `reprocess_skip: true` (сброс вручную в frontmatter).")
    else:
        lines.append("**Заметки для reprocess**: не найдено по паттерну из `config/reprocess.yaml`")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Сводный отчёт по тегам и дублям (read-only)")
    ap.add_argument(
        "--vault",
        type=str,
        default="",
        help="Корень Obsidian vault (как VAULT_PATH). Если не задан — из окружения/конфига.",
    )
    ap.add_argument("--out", "-o", type=str, default="", help="Путь к .md файлу отчёта (относительно vault или абсолютный)")
    args = ap.parse_args()

    vault = _vault_root(args)
    _pp = str(AGENT_DIR)
    _existing = os.environ.get("PYTHONPATH", "")
    if _existing:
        _pp = f"{_pp}{os.pathsep}{_existing}"
    child_env = {**os.environ, "VAULT_PATH": str(vault), "PYTHONPATH": _pp}

    # Запускаем оба скрипта и собираем вывод
    tags_out = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "analyze_vault_tags.py")],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=600,
        env=child_env,
    )
    dups_out = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "analyze_vault_duplicates.py")],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=600,
        env=child_env,
    )

    import datetime

    from knowledge_bot.services.maintenance_metrics import build_dynamics_markdown_section

    maintenance_section = _build_maintenance_section(vault)
    dynamics_section = build_dynamics_markdown_section(vault)

    report_lines = [
        "# Аудит хранилища 700_База_Данных",
        "",
        f"Обновлён: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## 1. Теги",
        "",
        "```",
        tags_out.stdout if tags_out.returncode == 0 else tags_out.stderr or "Ошибка",
        "```",
        "",
        "---",
        "",
        "## 2. Дубли (_1, _2, _3)",
        "",
        "```",
        dups_out.stdout if dups_out.returncode == 0 else dups_out.stderr or "Ошибка",
        "```",
        "",
        "---",
        "",
        maintenance_section,
        "---",
        "",
        dynamics_section,
    ]

    report_text = "\n".join(report_lines)

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = vault / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")
        print(f"Отчёт записан: {out_path}")
    else:
        print(report_text)


if __name__ == "__main__":
    main()
