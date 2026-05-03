#!/usr/bin/env python3
"""
Перетегирование заметок, у которых ≥1 тег встречается только в 1-2 заметках.

LLM получает ТОЛЬКО инвентарь тегов с count≥2, чтобы не плодить новые синглтоны.
Дешёвый скрипт: нет ASR/Vision, только текст заметки + тег-промпт.

  python retag_notes.py              # превью (dry-run), первые 20 «самых плохих»
  python retag_notes.py --apply      # записать
  python retag_notes.py --all        # единоразовый прогон ВСЕХ подходящих заметок
  python retag_notes.py --limit 10   # не больше 10 заметок
  python retag_notes.py --threshold 2  # считать «плохим» тег с count <= N (дефолт: 2)
  python retag_notes.py --strip-singleton-topics  # убрать старые topic/*-синглтоны после добавления topic от LLM
  python retag_notes.py --vault /path
"""
from __future__ import annotations

# ── bootstrap .env ──────────────────────────────────────────────────────────
from pathlib import Path

_pkg = Path(__file__).resolve().parent.parent
for _p in (_pkg / ".env", _pkg.parent / ".env"):
    if _p.exists():
        for _l in _p.read_text(encoding="utf-8", errors="ignore").splitlines():
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                import os; k, _, v = _l.partition("="); os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        break

import json
import re
import sys
import yaml

sys.path.insert(0, str(_pkg.parent))

from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.core.settings import load_prompt, load_enums_config, get_author_context
from knowledge_bot.services.tags_inventory import (
    scan_all_notes,
    get_tags_inventory_for_prompt_restricted,
    update_inventory_with_new_tags,
)

# ── helpers ──────────────────────────────────────────────────────────────────

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_fm(text: str) -> tuple[dict, str]:
    import yaml
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        return yaml.safe_load(m.group(1)) or {}, text[m.end():]
    except Exception:
        return {}, text


def _dump_fm(fm: dict, body: str) -> str:
    import yaml
    return "---\n" + yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False) + "---\n" + body


def _note_summary(fm: dict, body: str) -> str:
    """Краткое текстовое представление заметки для тег-промпта."""
    parts = []
    for key in ("title", "summary", "description", "keywords", "topic"):
        if fm.get(key):
            parts.append(f"{key}: {fm[key]}")
    # первые 800 символов тела
    clean = re.sub(r"!\[\[.*?\]\]|\[\[.*?\]\]", "", body).strip()
    if clean:
        parts.append("body: " + clean[:800])
    return "\n".join(parts) or "(нет контента)"


def _slug(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _normalize_tags(raw: list, enums_cfg, existing_inv: dict) -> list[str]:
    """Базовая нормализация тегов — та же логика что в bot.py."""
    result = []
    for tag in raw:
        if not isinstance(tag, str) or "/" not in tag:
            continue
        ns, _, val = tag.strip().partition("/")
        ns = ns.lower()
        val_slug = _slug(val)
        if not val_slug:
            continue
        # Сверяем с синонимами из enums
        syns = (enums_cfg.synonyms or {}).get(ns, {})
        for canon, aliases in syns.items():
            if val_slug in ([_slug(a) for a in (aliases if isinstance(aliases, list) else [aliases])]):
                val_slug = _slug(canon)
                break
        result.append(f"{ns}/{val_slug}")
    # Дедупликация, сортировка
    return sorted(dict.fromkeys(result))


# ── candidate selection ──────────────────────────────────────────────────────

def _find_candidates(
    vault: Path,
    inv: dict,
    threshold: int,
    target_dirs: list[str] | None = None,
) -> list[tuple[Path, list[str]]]:
    """
    Возвращает список (path, bad_tags) — заметки, у которых ≥1 тег с count <= threshold.
    Сортировка: сначала заметки с наибольшим числом плохих тегов.
    """
    tags_info: dict = inv.get("tags", {})
    dirs = target_dirs or ["700_База_Данных"]
    candidates: list[tuple[Path, list[str], int, bool]] = []

    for d in dirs:
        for md in (vault / d).rglob("*.md"):
            if md.name.startswith("🗺️"):  # skip hubs
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            fm, _ = _parse_fm(text)
            tags = fm.get("tags") or []
            if not isinstance(tags, list):
                continue
            bad = [t for t in tags if isinstance(t, str) and tags_info.get(t, {}).get("count", 0) <= threshold]
            if bad:
                all_tags = [t for t in tags if isinstance(t, str)]
                all_bad = len(all_tags) > 0 and len(bad) == len(all_tags)
                candidates.append((md, bad, len(bad), all_bad))

    # Сначала заметки, где все теги «плохие» (часто только синглтоны), затем по числу плохих тегов
    candidates.sort(key=lambda x: (-int(x[3]), -x[2], str(x[0])))
    return [(p, b) for p, b, _, _ in candidates]


# ── main ─────────────────────────────────────────────────────────────────────

def retag_notes(
    *,
    vault: Path,
    cfg,
    limit: int | None,
    threshold: int,
    apply: bool,
    verbose: bool = False,
    strip_obsolete_singleton_topics: bool = False,
) -> dict:
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    enums_cfg = load_enums_config(cfg.agent_config_path)

    # Инвентарь: сканируем свежий (чтобы учесть предыдущие прогоны)
    inv = scan_all_notes(vault)
    candidates = _find_candidates(vault, inv, threshold=threshold)

    ontology_mappings: dict[str, str] = {}
    ont_path = cfg.agent_config_path / "tag_ontology.yaml"
    if ont_path.exists():
        try:
            oc = yaml.safe_load(ont_path.read_text(encoding="utf-8")) or {}
            m = oc.get("mappings") or {}
            if isinstance(m, dict):
                ontology_mappings = {str(k): str(v) for k, v in m.items()}
        except Exception:
            ontology_mappings = {}

    if limit is not None:
        candidates = candidates[:limit]

    print(f"Заметок для перетегирования (threshold≤{threshold}): {len(candidates)}")
    if not candidates:
        return {"ok": True, "touched": 0, "skipped": 0}

    # Промпт для тегов + ограниченный инвентарь (только count≥2)
    tags_system = load_prompt(cfg.agent_config_path, "tags")
    ctx = get_author_context(cfg.agent_config_path)
    if ctx:
        tags_system = tags_system.replace("{{AUTHOR_CONTEXT_LINE}}", f"Учти личность автора: {ctx}\n\n")
    else:
        tags_system = tags_system.replace("{{AUTHOR_CONTEXT_LINE}}", "")

    # Используем ТОЛЬКО теги с count≥2 — LLM не должен предлагать новые синглтоны
    restricted_inv = get_tags_inventory_for_prompt_restricted(cfg.agent_config_path, min_count=2)
    tags_system = f"{tags_system}\n\n{restricted_inv}"

    # Множество "устоявшихся" тегов (count > threshold) для фильтрации LLM-предложений
    established: set[str] = {
        t for t, info in inv.get("tags", {}).items()
        if (info.get("count") or 0) > threshold
    }

    touched, skipped = 0, 0
    changed_tags: dict[str, list[str]] = {}

    for path, bad_tags in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        fm, body = _parse_fm(text)
        old_tags: list[str] = fm.get("tags") or []
        tags_info: dict = inv.get("tags", {})

        # Теги которые уже хорошие — сохраняем без изменений
        good_original = [t for t in old_tags if (tags_info.get(t, {}).get("count") or 0) > threshold]

        summary = _note_summary(fm, body)
        tags_user = {
            "type": fm.get("type", "unknown"),
            "summary": {"raw_text": summary, "derived": {}},
            "attachments": {"links": []},
            "enums": {
                "namespaces_controlled": enums_cfg.namespaces_controlled,
                "common": enums_cfg.common,
                "per_type": enums_cfg.per_type,
            },
            "synonyms": enums_cfg.synonyms,
            "filenames": [],
            "fields": {k: v for k, v in fm.items()
                       if k not in {"type", "title", "created", "tags", "attachments"}},
        }

        try:
            resp = llm.chat_json(tags_system, json.dumps(tags_user, ensure_ascii=False), timeout=60.0)
            raw = (resp.content or []) if resp else []
            if isinstance(raw, dict) and "tags" in raw:
                raw = raw["tags"]
            if not isinstance(raw, list):
                raw = []
        except Exception as e:
            print(f"  ⚠ LLM error for {path.name}: {e}")
            skipped += 1
            continue

        llm_tags = _normalize_tags(raw, enums_cfg, inv)
        llm_tags = list(dict.fromkeys(ontology_mappings.get(t, t) for t in llm_tags))

        # Принимаем LLM-тег только если он уже есть в established инвентаре
        # (иначе создадим новый синглтон, что контрпродуктивно). Переносы из tag_ontology.yaml —
        # чтобы LLM мог выбрать синоним, а мы приняли канонический устоявшийся тег.
        accepted_from_llm = [t for t in llm_tags if t in established and t not in old_tags]

        # Стратегия: ТОЛЬКО ДОБАВЛЯЕМ established теги поверх оригинальных.
        # Ничего не удаляем — нельзя терять семантику (topic/evolution в "Эгоистичном гене" важен,
        # даже если он singleton). Постепенно синглтоны либо наберут count сами, либо
        # войдут в tag_ontology mappings (run propose → apply вручную).
        if not accepted_from_llm:
            if verbose:
                print(f"  = {path.name}: LLM не добавил новых established тегов, пропускаем")
            skipped += 1
            continue

        # Объединяем: все оригинальные + новые established от LLM
        new_tags = list(dict.fromkeys(old_tags + accepted_from_llm))

        # Снять устаревшие topic/* с count≤threshold, если LLM добавил другой устоявшийся topic/*
        if strip_obsolete_singleton_topics and accepted_from_llm:
            added_topic_established = [
                t for t in accepted_from_llm
                if isinstance(t, str) and t.startswith("topic/") and t in established
            ]
            if added_topic_established:
                new_tags = [
                    t for t in new_tags
                    if not (
                        isinstance(t, str)
                        and t.startswith("topic/")
                        and (tags_info.get(t, {}).get("count") or 0) <= threshold
                        and t not in accepted_from_llm
                    )
                ]

        new_tags = sorted(dict.fromkeys(new_tags))

        if sorted(new_tags) == sorted(old_tags):
            if verbose:
                print(f"  = {path.name}: теги не изменились")
            skipped += 1
            continue

        rel = str(path.relative_to(vault))
        print(f"  {'✏' if apply else '~'} {rel}")
        print(f"    было:  {old_tags}")
        print(f"    стало: {new_tags}")
        if verbose:
            print(f"    плохих было: {bad_tags}")
            print(f"    LLM предложил: {llm_tags}  →  принято: {accepted_from_llm}")

        fm["tags"] = new_tags
        changed_tags[rel] = new_tags

        if apply:
            path.write_text(_dump_fm(fm, body), encoding="utf-8")
            update_inventory_with_new_tags(cfg.agent_config_path, new_tags)

        touched += 1

    print(f"\nИтого: затронуто={touched}, пропущено={skipped}")
    return {"ok": True, "touched": touched, "skipped": skipped, "changed": changed_tags}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Перетегировать заметки с редкими тегами через LLM")
    ap.add_argument("--apply", action="store_true", help="Записать изменения (без флага — dry-run)")
    ap.add_argument("--all", dest="all_notes", action="store_true", help="Прогнать все подходящие (без лимита)")
    ap.add_argument("--limit", type=int, default=20, help="Максимум заметок (дефолт 20, --all отменяет)")
    ap.add_argument("--threshold", type=int, default=1, help="count≤N считается плохим тегом (дефолт 1: только синглтоны)")
    ap.add_argument("--vault", type=str, default="", help="Путь к vault")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--strip-singleton-topics",
        action="store_true",
        help="После добавления topic/* от LLM убрать старые topic/* с count≤threshold",
    )
    args = ap.parse_args()

    if args.vault:
        import os; os.environ["VAULT_PATH"] = args.vault

    cfg = load_config()
    limit = None if args.all_notes else args.limit

    retag_notes(
        vault=cfg.vault_path,
        cfg=cfg,
        limit=limit,
        threshold=args.threshold,
        apply=args.apply,
        verbose=args.verbose,
        strip_obsolete_singleton_topics=args.strip_singleton_topics,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
