#!/usr/bin/env python3
"""
Перегнать заметки с generic/артефактными названиями через полный пайплайн,
как будто их только что кинули в бота.

Матчится по пути/имени файла в папках Видео, Знания, Песни, Ссылки.

  python reprocess_notes.py              # превью
  python reprocess_notes.py --apply      # записать; заметки без контента — удалить
  python reprocess_notes.py --vault /path/to/vault
  python reprocess_notes.py --limit 5    # только первые 5 заметок
  python reprocess_notes.py --verbose    # вывод asr/vision, логов и причин пропуска

При 429 (Vision лимит) — скрипт сразу завершает работу.
"""
from __future__ import annotations

# Подгрузка .env
from pathlib import Path
for _p in [Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent / ".env"]:
    if _p.exists():
        for _line in _p.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                import os
                os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
        break

import json
import re
import sys
import yaml
from pathlib import Path

# Add parent for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config
from extract import extract_from_path, fetch_youtube_transcript, VisionRateLimitError
from llm import LLMClient
from persist import write_note
from render import render_note
from routing import route_and_fill
from schema import allowed_fields_for_type
from settings import load_prompt, load_enums_config, get_author_context
from tags_inventory import get_tags_inventory_for_prompt, update_inventory_with_new_tags


def parse_note(note_path: Path) -> tuple[dict, str]:
    """Парсит заметку: frontmatter dict и body."""
    import yaml
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except Exception:
        data = {}
    body = text[m.end():]
    return data, body


def extract_media_from_body(body: str, vault_path: Path) -> Path | None:
    """Ищет путь к медиа (![[path]] или - [[path]]) в body. Возвращает первый найденный."""
    for p in extract_all_linked_files(body):
        full = vault_path / p
        if full.exists() and full.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov", ".webm", ".mp3", ".m4a", ".wav"}:
            return full
    return None


def extract_all_linked_files(body: str) -> list[str]:
    """Извлекает ВСЕ пути к файлам из body (![[path]], - [[path|name]])."""
    paths = []
    for pattern in [r"!\[\[([^\]]+)\]\]", r"- \[\[([^\]|]+)(?:\|[^\]]*)?\]\]"]:
        for m in re.finditer(pattern, body):
            path_str = m.group(1).strip()
            if "|" in path_str:
                path_str = path_str.split("|", 1)[0].strip()
            if path_str and path_str not in paths:
                paths.append(path_str)
    return paths


def extract_youtube_urls(fm: dict, body: str) -> list[str]:
    """Извлекает YouTube URL из заметки (attachments.links, body)."""
    urls = []
    for u in (fm.get("attachments", {}) or {}).get("links", []) or []:
        if isinstance(u, str) and ("youtube.com" in u or "youtu.be" in u):
            urls.append(u)
    for m in re.finditer(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)[^\s)\]\"']+", body):
        urls.append(m.group(0))
    return list(dict.fromkeys(urls))  # без дубликатов


def extract_all_links_from_body(body: str) -> list[str]:
    """Извлекает все https URL из body (для заметок без media)."""
    return list(dict.fromkeys(m.group(0) for m in re.finditer(r"https?://[^\s)\]\"']+", body)))


def _extract_raw_from_body(body: str, for_media_note: bool = False) -> str:
    """Исходный текст из body: URL или короткая подпись. Для медиа — не подставляем body."""
    if for_media_note:
        return ""
    for m in re.finditer(r"https?://[^\s)\]\"']+", body):
        return m.group(0)
    lines = body.split("\n")
    for ln in lines:
        ln = ln.strip()
        if ln and not ln.startswith("#") and not ln.startswith("-") and not ln.startswith("[["):
            if len(ln) > 300 or "## " in ln or "[[" in ln:
                return ""  # не весь body/разметку
            return ln
    return ""


def extract_sections(body: str) -> dict[str, str]:
    """Извлекает ## Секции из body."""
    sections = {}
    for m in re.finditer(r"^##\s+(.+?)\s*$", body, re.MULTILINE):
        name = m.group(1).strip()
        start = m.end()
        next_m = re.search(r"^##\s+", body[m.end():], re.MULTILINE)
        end = m.end() + next_m.start() if next_m else len(body)
        sections[name] = body[start:end].strip()
    return sections


def main() -> None:
    import os
    import logging
    apply = "--apply" in sys.argv or "-apply" in sys.argv
    verbose = "--verbose" in sys.argv
    limit = None
    vault_override = None
    for i, a in enumerate(sys.argv):
        if a == "--vault" and i + 1 < len(sys.argv):
            vault_override = Path(sys.argv[i + 1]).resolve()
        elif a == "--limit" and i + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[i + 1])
            except ValueError:
                limit = 5
    if vault_override:
        os.environ["VAULT_PATH"] = str(vault_override)
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
    cfg = load_config()
    vault = vault_override or cfg.vault_path
    db_root = vault / "700_База_Данных"
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)

    # Паттерны из config/reprocess.yaml
    reprocess_cfg_path = cfg.agent_config_path / "reprocess.yaml"
    if reprocess_cfg_path.exists():
        reprocess_cfg = yaml.safe_load(reprocess_cfg_path.read_text(encoding="utf-8")) or {}
    else:
        reprocess_cfg = {}
    bad_pattern = reprocess_cfg.get("bad_stem_pattern", r"^(IMG|YouTube|Без_названия|Субтитры|Редактор_субтитров|Динамичная_музыка|Позитивная_музыка|Позитивирующая_музыка|Спокойная_музыка|OCR_текст)")
    allowed_folders = set(reprocess_cfg.get("allowed_folders", ["Видео", "Знания", "Песни", "Ссылки"]))
    RE_BAD = re.compile(bad_pattern, re.I)

    candidates = []
    for note_path in db_root.rglob("*.md"):
        if "Export" in str(note_path):
            continue
        try:
            rel = note_path.relative_to(db_root)
        except ValueError:
            continue
        parts = rel.parts
        if not parts or parts[0] not in allowed_folders:
            continue
        stem = note_path.stem
        if not RE_BAD.search(stem):
            continue
        fm, body = parse_note(note_path)
        candidates.append((note_path, fm, body))

    if limit:
        candidates = candidates[:limit]
        print(f"Обрабатываем (limit={limit}): {len(candidates)}")
    else:
        print(f"Найдено заметок: {len(candidates)}")
    if not candidates:
        print(f"  (vault: {vault}, db_root exists: {db_root.exists()})")
        return

    # Диагностика vision (для видео)
    has_vision_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    if any(extract_media_from_body(b, vault) for _, _, b in candidates):
        print(f"  Vision (сцена): {'✓ OPENROUTER_API_KEY задан' if has_vision_key else '✗ OPENROUTER_API_KEY не задан — добавь в .env для описания кадров'}")
    print()

    for note_path, fm, body in candidates:
        rel = note_path.relative_to(vault)
        print(f"\n--- {rel} ---")
        media_path = extract_media_from_body(body, vault)
        sections = extract_sections(body)

        summary_obj = {"raw_text": "", "meta": {"form": "video" if media_path else "text"}, "derived": {}}
        if media_path:
            try:
                derived = extract_from_path(str(media_path), llm_client=llm)
                summary_obj["derived"]["asr_text"] = derived.asr_text
                summary_obj["derived"]["vision_text"] = derived.vision_text
                summary_obj["derived"]["ocr_text"] = derived.ocr_text
            except VisionRateLimitError as e:
                print(f"\n\n⚠️ {e} — останавливаем reprocess.")
                sys.exit(1)
        if "Транскрипция" in sections:
            summary_obj["derived"]["asr_text"] = summary_obj["derived"].get("asr_text", "") + "\n" + sections["Транскрипция"]
        if "Сводка (ASR)" in sections:
            summary_obj["derived"]["asr_summary"] = sections["Сводка (ASR)"]
        if "Исходный текст" in sections:
            _rt = sections["Исходный текст"].strip()
            if len(_rt) > 400 or ("## " in _rt and "[[" in _rt):
                _rt = ""
            summary_obj["raw_text"] = _rt
        # YouTube transcript — для заметок со ссылками на ютуб (особенно без локального видео)
        yt_urls = extract_youtube_urls(fm, body)
        if yt_urls:
            yt_text = fetch_youtube_transcript(yt_urls[0])
            if yt_text:
                summary_obj["derived"]["yt_transcript_text"] = yt_text
                # Суммаризация через LLM
                try:
                    yt_system = load_prompt(cfg.agent_config_path, "yt_transcript_summary")
                    yt_user = json.dumps({"asr_text": yt_text, "type": summary_obj["meta"].get("form", "video")}, ensure_ascii=False)
                    yt_resp = llm.chat_json(yt_system, yt_user).content or {}
                    if isinstance(yt_resp, dict) and yt_resp.get("asr_summary"):
                        summary_obj["derived"]["yt_transcript_summary"] = yt_resp["asr_summary"].strip()
                except Exception as yt_err:
                    pass  # без падения, просто не будет summary
        summary_obj["derived"] = {k: (v or "").strip() for k, v in summary_obj["derived"].items() if v}

        # Пропуск заметок без контента — не перезаписывать пустыми данными
        orig_att = fm.get("attachments", {}) or {}
        orig_files_pre = [str(p) for p in (orig_att.get("files") or []) if p]
        orig_links_pre = [str(u) for u in (orig_att.get("links") or []) if u]
        body_files_pre = extract_all_linked_files(body)
        body_links_pre = extract_all_links_from_body(body)
        has_any = (
            bool(media_path)
            or bool(yt_urls)
            or bool(orig_files_pre)
            or bool(orig_links_pre)
            or bool(body_files_pre)
            or bool(body_links_pre)
            or any(summary_obj["derived"].values())
            or bool(summary_obj.get("raw_text", "").strip())
        )
        if not has_any:
            why = f"media={bool(media_path)} files={len(orig_files_pre)+len(body_files_pre)} links={len(orig_links_pre)+len(body_links_pre)+len(yt_urls or [])} derived={bool(summary_obj['derived'])}"
            if apply:
                try:
                    note_path.unlink()
                    print(f"  [удалено: нет контента] ({why})")
                except FileNotFoundError:
                    print(f"  [уже удалено] ({why})")
                except Exception as e:
                    print(f"  [ошибка удаления: {e}] ({why})")
            else:
                print(f"  [будет удалено: нет контента] ({why})")
            if verbose:
                preview = (body[:150] + "…") if len(body) > 150 else (body or "(пусто)")
                print(f"    media_path: {media_path or 'None'}")
                print(f"    attachments.files: {orig_files_pre or '(пусто)'}")
                print(f"    attachments.links: {orig_links_pre or '(пусто)'}")
                print(f"    body_files: {body_files_pre or '(пусто)'}")
                print(f"    body_links: {body_links_pre or '(пусто)'}")
                print(f"    yt_urls: {yt_urls or '(пусто)'}")
                print(f"    derived: {list(summary_obj['derived'].keys()) or '(пусто)'}")
                print(f"    body: {preview!r}")
            continue

        # Вывод всех обогащений — что реально уходит в routing/naming
        def _trunc(s: str, n: int = 400) -> str:
            if not s:
                return "(пусто)"
            return s[:n] + ("..." if len(s) > n else "")
        der = summary_obj.get("derived", {})
        print("  [обогащения]")
        vision_val = der.get("vision_text", "")
        print(f"    asr_text: {_trunc(der.get('asr_text', ''))}")
        print(f"    vision_text: {_trunc(vision_val)}" + (" ← OPENROUTER_API_KEY не задан?" if media_path and not vision_val and not has_vision_key else ""))
        print(f"    ocr_text: {_trunc(der.get('ocr_text', ''))}")
        print(f"    asr_summary: {_trunc(der.get('asr_summary', ''))}")
        print(f"    yt_transcript_text: {_trunc(der.get('yt_transcript_text', ''))}")
        print(f"    yt_transcript_summary: {_trunc(der.get('yt_transcript_summary', ''))}")
        print(f"    raw_text: {_trunc(summary_obj.get('raw_text', ''))}")
        print(f"    filenames: {fm.get('attachments', {}).get('files', []) or []}")

        routed = route_and_fill(llm, summary_obj, source_hint="telegram")
        # БАЗА: всё из оригинальной заметки
        orig_att = fm.get("attachments", {}) or {}
        orig_files = orig_files_pre
        orig_links = orig_links_pre
        body_files = body_files_pre
        body_links = body_links_pre
        all_files = list(dict.fromkeys(orig_files + [p for p in body_files if p not in orig_files]))
        all_links = list(dict.fromkeys(orig_links + (yt_urls or []) + body_links))
        if media_path:
            try:
                rel_media = str(media_path.relative_to(vault))
                if rel_media not in all_files:
                    all_files.insert(0, rel_media)
            except ValueError:
                pass
        # Сохраняем оригинальные поля (кроме type/title/tags — их задаёт наш пайплайн)
        _str_fields = {"author", "rating", "status", "summary", "source", "form", "raw_dir"}
        for k, v in fm.items():
            if k in ("type", "title", "tags"):
                continue
            if k not in routed or routed[k] in (None, "", [], {}):
                if v is None or (isinstance(v, str) and str(v).strip().lower() == "none"):
                    v = "" if k in _str_fields else v
                routed[k] = v
        routed["attachments"] = {"files": all_files or [], "links": all_links or []}
        if media_path:
            try:
                routed["raw_dir"] = str(media_path.relative_to(vault).parent)
            except ValueError:
                routed["raw_dir"] = fm.get("raw_dir", "")
        elif not routed.get("raw_dir"):
            routed["raw_dir"] = fm.get("raw_dir", "")
        if summary_obj["derived"].get("yt_transcript_summary"):
            routed["yt_transcript_summary"] = summary_obj["derived"]["yt_transcript_summary"]

        naming_system = load_prompt(cfg.agent_config_path, "naming")
        naming_input = json.dumps({
            "type": routed.get("type"),
            "summary": summary_obj,
            "filenames": all_files or fm.get("attachments", {}).get("files", []) or [],
            "hint_title": routed.get("title")
        }, ensure_ascii=False)
        named = llm.chat_json(naming_system, naming_input).content or {}
        if isinstance(named, dict) and isinstance(named.get("title"), str) and named["title"].strip():
            routed["title"] = named["title"].strip()

        enums_cfg = load_enums_config(cfg.agent_config_path)
        allowed_fields = allowed_fields_for_type(routed["type"]) or []
        if allowed_fields:
            field_system = load_prompt(cfg.agent_config_path, "field_fill")
            user = {
                "type": routed["type"],
                "allowed_fields": allowed_fields,
                "summary": summary_obj,
                "filenames": routed.get("filenames", []),
                "enums": {"namespaces_controlled": enums_cfg.namespaces_controlled, "common": enums_cfg.common, "per_type": enums_cfg.per_type},
            }
            filled = llm.chat_json(field_system, json.dumps(user, ensure_ascii=False)).content or {}
            for k in allowed_fields:
                if k in filled:
                    routed[k] = filled[k]

        tags_system = load_prompt(cfg.agent_config_path, "tags")
        ctx = get_author_context(cfg.agent_config_path)
        author_line = f"Учти личность автора: {ctx}\n\n" if ctx else ""
        tags_system = tags_system.replace("{{AUTHOR_CONTEXT_LINE}}", author_line)
        tags_system = f"{tags_system}\n\n{get_tags_inventory_for_prompt(cfg.agent_config_path)}"
        tags_user = {
            "type": routed.get("type"),
            "summary": summary_obj,
            "attachments": {"links": routed.get("attachments", {}).get("links", [])},
            "enums": {"namespaces_controlled": enums_cfg.namespaces_controlled, "common": enums_cfg.common, "per_type": enums_cfg.per_type},
            "synonyms": enums_cfg.synonyms,
            "filenames": routed.get("filenames", []),
            "fields": {k: v for k, v in routed.items() if k in allowed_fields},
        }
        tag_resp = llm.chat_json(tags_system, json.dumps(tags_user, ensure_ascii=False)).content or []
        routed["tags"] = sorted(dict.fromkeys(tag_resp.get("tags", []) if isinstance(tag_resp, dict) else (tag_resp if isinstance(tag_resp, list) else [])))
        # raw_text — краткий оригинал (URL/подпись), не весь body
        _raw = sections.get("Исходный текст", "").strip() or summary_obj.get("raw_text", "").strip()
        if len(_raw) > 400 or ("## " in _raw and "[[" in _raw):
            _raw = ""
        if not _raw:
            _raw = _extract_raw_from_body(body, for_media_note=bool(media_path))
        routed["raw_text"] = _raw
        # asr_summary: новый от LLM или оригинал из заметки
        routed["asr_summary"] = summary_obj["derived"].get("asr_summary", "").strip() or sections.get("Сводка (ASR)", "").strip()
        routed["asr_text"] = summary_obj["derived"].get("asr_text", "").strip() or sections.get("Транскрипция", "").strip()
        routed["created"] = fm.get("created") or routed.get("created", "")

        try:
            rendered = render_note(cfg.templates_path, routed)
        except Exception as e:
            print(f"  Ошибка render: {e}")
            continue

        print(f"  Было: {fm.get('title')} | type={fm.get('type')}")
        print(f"  Стало: {routed.get('title')} | type={routed.get('type')} | tags={routed.get('tags', [])[:5]}...")
        print(f"  [attachments] files={routed.get('attachments', {}).get('files', [])} links={len(routed.get('attachments', {}).get('links', []))} шт.")
        if verbose:
            print("  [полная заметка]\n" + (rendered[:3000] + "\n..." if len(rendered) > 3000 else rendered))
        if apply:
            new_path = write_note(vault, routed["type"], routed["title"], rendered)
            if new_path.resolve() != note_path.resolve():
                try:
                    note_path.unlink()
                except FileNotFoundError:
                    pass  # уже удалён (sync и т.п.)
            if routed.get("tags"):
                update_inventory_with_new_tags(cfg.agent_config_path, routed["tags"])
            print(f"  ✓ Записано: {new_path.relative_to(vault)}")


if __name__ == "__main__":
    main()
