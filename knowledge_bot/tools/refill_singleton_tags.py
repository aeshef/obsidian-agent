#!/usr/bin/env python3
"""
Чистка редких topic/* и прочих синглтонов: LLM решает ОСТАВИТЬ vs УБРАТЬ по смыслу.
Новые теги не добавляются (для добавления устоявшихся — retag_notes.py).

  python refill_singleton_tags.py              # dry-run
  python refill_singleton_tags.py --apply
  python refill_singleton_tags.py --apply --limit 10
  python refill_singleton_tags.py --all --apply   # весь backlog
  python refill_singleton_tags.py --topic-max-count 2
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

_pkg = Path(__file__).resolve().parent.parent
for _p in (_pkg / ".env", _pkg.parent / ".env"):
    if _p.exists():
        for _line in _p.read_text(encoding="utf-8", errors="ignore").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                if _k.strip():
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

sys.path.insert(0, str(_pkg.parent))

from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.core.settings import load_enums_config, load_prompt
from knowledge_bot.services.tag_normalize import normalize_tags
from knowledge_bot.services.tags_inventory import rebuild_inventory, scan_all_notes

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_note(path: Path) -> tuple[dict, str] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = _FM_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return None
    return fm, m.group(2)


def _is_rare_tag(tag: str, count: int, *, topic_max_count: int) -> bool:
    if not isinstance(tag, str) or not tag.strip():
        return False
    t = tag.strip()
    if t.startswith("topic/"):
        return count <= topic_max_count
    return count <= 1


def _find_candidates(
    vault: Path,
    inv: dict,
    *,
    topic_max_count: int,
) -> list[tuple[Path, dict, str, list[str], list[str]]]:
    """(path, fm, body, all_tags, rare_tags) — заметки с ≥1 редким тегом."""
    tags_data: dict = inv.get("tags", {})
    db_root = vault / "700_База_Данных"
    if not db_root.exists():
        return []

    out: list[tuple[Path, dict, str, list[str], list[str], int]] = []
    for path in sorted(db_root.rglob("*.md")):
        if "Export" in path.parts or path.name.startswith("🗺️"):
            continue
        parsed = _parse_note(path)
        if not parsed:
            continue
        fm, body = parsed
        tags = fm.get("tags", [])
        if not isinstance(tags, list):
            continue
        all_tags = [str(t).strip() for t in tags if t]
        rare: list[str] = []
        for t in all_tags:
            c = int(tags_data.get(t, {}).get("count") or 0)
            if _is_rare_tag(t, c, topic_max_count=topic_max_count):
                rare.append(t)
        if rare:
            out.append((path, fm, body, all_tags, rare, len(rare)))

    out.sort(key=lambda x: (-x[5], -len(x[4]), str(x[0])))
    return [(p, fm, body, at, rt) for p, fm, body, at, rt, _ in out]


def refill_singleton_tags(
    *,
    vault: Path,
    cfg,
    limit: int | None,
    apply: bool,
    topic_max_count: int = 2,
    verbose: bool = False,
) -> dict:
    if apply:
        from shared.llm_reachable import deepseek_api_reachable

        if not deepseek_api_reachable():
            print(
                "⚠️ api.deepseek.com недоступен — refill_singleton пропущен.\n"
                "   Повтори: FORCE_VAULT_MAINTENANCE=1 obsidian_sync.sh"
            )
            return {"ok": False, "touched": 0, "skipped": 0, "network_skip": True}

    inv = scan_all_notes(vault)
    tags_data = inv.get("tags", {})
    candidates = _find_candidates(vault, inv, topic_max_count=topic_max_count)

    if limit is not None:
        candidates = candidates[:limit]

    print(
        f"Заметок с редкими тегами (topic/* count≤{topic_max_count}, прочие count≤1): "
        f"{len(candidates)}"
    )
    if not candidates:
        return {"ok": True, "touched": 0, "skipped": 0}

    if not cfg.deepseek_api_key:
        print("Нужен DEEPSEEK_API_KEY", file=sys.stderr)
        return {"ok": False, "touched": 0, "skipped": 0}

    system_prompt = load_prompt(cfg.agent_config_path, "refill_singleton_tags", required=True)
    if not system_prompt.strip():
        print(
            "Промпт config/prompts/refill_singleton_tags.txt пуст. "
            "Скопируйте из refill_singleton_tags.example.txt",
            file=sys.stderr,
        )
        return {"ok": False, "touched": 0, "skipped": 0}

    enums_cfg = load_enums_config(cfg.agent_config_path)
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    touched, skipped, llm_errors = 0, 0, 0

    for path, fm, body, current_tags, rare_tags in candidates:
        rel = path.relative_to(vault)
        note_type = fm.get("type") or "Знания"
        body_preview = (body.strip() or "")[:1500]
        tags_with_counts = [
            {"tag": t, "count": int(tags_data.get(t, {}).get("count") or 0)}
            for t in current_tags
        ]
        tags_user = {
            "type": note_type,
            "body_preview": body_preview,
            "current_tags_with_counts": tags_with_counts,
            "rare_tags_on_note": rare_tags,
        }
        try:
            tag_resp = llm.chat_json(
                system_prompt,
                json.dumps(tags_user, ensure_ascii=False),
                timeout=60.0,
            ).content
        except Exception as e:
            print(f"  ⚠ {rel}: LLM error — {e}", file=sys.stderr)
            llm_errors += 1
            continue

        if isinstance(tag_resp, dict) and tag_resp.get("error") == "llm_unavailable":
            llm_errors += 1
            skipped += 1
            continue

        if isinstance(tag_resp, dict) and "tags" in tag_resp:
            tag_candidates = tag_resp.get("tags") or []
        else:
            tag_candidates = tag_resp if isinstance(tag_resp, list) else []

        new_tags = normalize_tags(
            tag_candidates,
            enums_cfg,
            note_type,
            allowed_tags=set(current_tags),
        )
        if not new_tags:
            new_tags = list(current_tags)

        removed = sorted(set(current_tags) - set(new_tags))
        if set(new_tags) == set(current_tags):
            if verbose:
                print(f"  = {rel}: без изменений")
            skipped += 1
            continue

        print(f"  {'✏' if apply else '~'} {rel}")
        print(f"    было:  {current_tags}")
        print(f"    стало: {new_tags}")
        if removed:
            print(f"    убрано: {removed}")

        if apply:
            fm["tags"] = new_tags
            buf = __import__("io").StringIO()
            yaml.dump(fm, buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            path.write_text("---\n" + buf.getvalue().strip() + "\n---\n" + body, encoding="utf-8")
            touched += 1
        else:
            touched += 1  # dry-run: считаем как «затронуто» для отчёта

    if apply and touched:
        try:
            rebuild_inventory()
        except Exception as exc:
            print(f"  ⚠ rebuild_inventory: {exc}")

    print(f"\nИтого refill: затронуто={touched}, пропущено={skipped}, llm_errors={llm_errors}")
    return {
        "ok": True,
        "touched": touched,
        "skipped": skipped,
        "llm_errors": llm_errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Оставить/убрать редкие topic/* и синглтоны по решению LLM",
    )
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--all", dest="all_notes", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--topic-max-count", type=int, default=2)
    ap.add_argument("--vault", type=str, default="")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.vault:
        os.environ["VAULT_PATH"] = args.vault

    cfg = load_config()
    limit = None if args.all_notes else args.limit

    result = refill_singleton_tags(
        vault=cfg.vault_path,
        cfg=cfg,
        limit=limit,
        apply=args.apply,
        topic_max_count=args.topic_max_count,
        verbose=args.verbose,
    )
    if result.get("network_skip"):
        return 3
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
