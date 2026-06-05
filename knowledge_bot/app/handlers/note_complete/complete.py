from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import date
from typing import Any

from aiogram.types import Message

from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.core.schema import allowed_fields_for_type
from knowledge_bot.core.settings import get_author_context, load_enums_config, load_prompt
from knowledge_bot.services.extract import extract_from_path, fetch_youtube_transcript, simple_from_text
from knowledge_bot.services.render import render_note
from knowledge_bot.services.routing import route_and_fill
from knowledge_bot.services.tags_inventory import get_tags_inventory_for_prompt
from knowledge_bot.services.wikilinks import inject_wikilinks

from knowledge_bot.app import state as app_state
from knowledge_bot.app.state import (
    cleanup_media_group_after_delay,
    get_asr_semaphore,
    get_message_rate_limiter,
    pending_limit,
    preview_keyboard,
)
from knowledge_bot.app.handlers.media import process_single_media
from knowledge_bot.app.handlers.review import generate_note_review


async def process_complete(main_message: Message, all_messages: list[Message], combined_text: str, media_group_id: int | None, log: logging.Logger, *, bulk_mode: bool = False) -> None:
    """Полная обработка сообщения(й) - от медиа до отправки review"""
    cfg = load_config()
    
    # Отправляем промежуточное сообщение сразу, чтобы пользователь видел, что бот работает
    try:
        processing_msg = await main_message.answer("⏳ Обрабатываю...")
    except Exception as proc_err:
        log.warning("Failed to send processing message: %s", proc_err)
        processing_msg = None
    bundle = simple_from_text(combined_text)

    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    summary_obj = bundle.to_summary()
    summary_obj["meta"] = summary_obj.get("meta", {})
    
    # YouTube: транскрипт без загрузки (для ссылок на ролики)
    all_urls = list(bundle.urls or [])
    for msg in all_messages:
        txt = msg.text or msg.caption or ""
        ents = getattr(msg, "entities", None) or getattr(msg, "caption_entities", None) or []
        for ent in ents:
            if getattr(ent, "type", "") == "text_link" and getattr(ent, "url", ""):
                all_urls.append(ent.url)
            elif getattr(ent, "type", "") == "url" and txt:
                start, length = getattr(ent, "offset", 0), getattr(ent, "length", 0)
                all_urls.append(txt[start:start + length])
    yt_url = next((u for u in all_urls if u and ("youtube.com" in u or "youtu.be" in u)), None)
    if yt_url:
        try:
            yt_text = await asyncio.to_thread(fetch_youtube_transcript, yt_url)
            if yt_text:
                summary_obj["derived"]["yt_transcript_text"] = yt_text
                log.info("YouTube transcript: %d chars", len(yt_text))
        except Exception as yt_err:
            log.warning("YouTube transcript failed: %s", yt_err)
    
    # НЕ делаем роутинг сразу - сначала загрузим медиа и извлечем OCR/ASR
    # Роутинг будет после загрузки медиа на основе полного контекста
    routed = {"type": None, "attachments": {"links": [], "files": []}, "form": None}
    summary_obj["derived"] = summary_obj.get("derived", {})
    
    # Обрабатываем все медиа из группы (или одно сообщение)
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    for msg in all_messages:
        await process_single_media(msg, combined_text, routed, summary_obj, llm, cfg, log)
    
    # Ре-роутинг после обработки всех медиа, если есть OCR/ASR/PDF/vision/yt_transcript
    has_derived = any(summary_obj["derived"].get(k) for k in ("ocr_text", "asr_text", "pdf_text", "vision_text", "yt_transcript_text"))
    if has_derived and not routed.get("type"):
        try:
            rerouted = route_and_fill(llm, summary_obj, source_hint="telegram")
            rerouted.setdefault("attachments", {"links": [], "files": []})
            routed.setdefault("attachments", {"links": [], "files": []})
            old_links = set(routed["attachments"].get("links", []) or [])
            new_links = set(rerouted["attachments"].get("links", []) or [])
            rerouted["attachments"]["links"] = sorted(old_links | new_links)
            old_files = routed["attachments"].get("files", []) or []
            new_files = rerouted["attachments"].get("files", []) or []
            rerouted["attachments"]["files"] = new_files + [f for f in old_files if f not in new_files]
            if routed.get("filenames"):
                rerouted.setdefault("filenames", []).extend([n for n in routed["filenames"] if n not in (rerouted.get("filenames") or [])])
            if routed.get("raw_dir"):
                rerouted["raw_dir"] = routed["raw_dir"]
            if routed.get("form"):
                rerouted["form"] = routed["form"]
            routed = rerouted
            log.info("Re-routed after media processing: type=%s", routed.get("type"))
        except Exception as re_err:
            log.warning("reroute after media processing failed: %s", re_err)
    
    # ASR: расшифровка в заметку (видео и голос/аудио) и сводка для видео
    if summary_obj["derived"].get("asr_text"):
        routed["asr_text"] = summary_obj["derived"]["asr_text"]
        if routed.get("form") == "video":
            try:
                asr_system = load_prompt(cfg.agent_config_path, "asr_summary")
                asr_user = {"asr_text": summary_obj["derived"]["asr_text"], "type": routed.get("type")}
                asr_resp = llm.chat_json(asr_system, json.dumps(asr_user, ensure_ascii=False)).content or {}
                if isinstance(asr_resp, dict) and isinstance(asr_resp.get("asr_summary"), str):
                    routed["asr_summary"] = asr_resp["asr_summary"].strip()
            except Exception as sum_err:
                log.warning("ASR summarize failed: %s", sum_err)
    
    # YouTube transcript summary (для ссылок на ролики без загрузки)
    if summary_obj["derived"].get("yt_transcript_text"):
        try:
            yt_system = load_prompt(cfg.agent_config_path, "yt_transcript_summary")
            yt_user = {"asr_text": summary_obj["derived"]["yt_transcript_text"], "type": routed.get("type")}
            yt_resp = llm.chat_json(yt_system, json.dumps(yt_user, ensure_ascii=False)).content or {}
            if isinstance(yt_resp, dict) and isinstance(yt_resp.get("asr_summary"), str):
                summary_obj["derived"]["yt_transcript_summary"] = yt_resp["asr_summary"].strip()
                routed["yt_transcript_summary"] = summary_obj["derived"]["yt_transcript_summary"]
                log.info("YouTube transcript summarized: %d chars", len(summary_obj["derived"]["yt_transcript_summary"]))
                log.info("[DEBUG yt] routed['yt_transcript_summary'] set, len=%d", len(routed["yt_transcript_summary"]))
                # Освободить память: полный транскрипт больше не нужен после суммаризации
                try:
                    summary_obj["derived"].pop("yt_transcript_text", None)
                except Exception:
                    pass
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
        except Exception as yt_sum_err:
            log.warning("YouTube transcript summarize failed: %s", yt_sum_err)
    
    # Fallback for heavy video via yt-dlp when Telegram refuses to download large files
    try:
        if os.environ.get("YTDLP_ENABLED", "0") == "1":
            has_files = bool((routed.get("attachments", {}) or {}).get("files"))
            ytdlp_url = None
            if not has_files:
                for u in routed.get("attachments", {}).get("links", []) or []:
                    if any(d in u for d in ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "x.com", "twitter.com")):
                        ytdlp_url = u
                        break
            if ytdlp_url:
                from knowledge_bot.services.extract.youtube import download_via_ytdlp
                saved_path = download_via_ytdlp(ytdlp_url, cfg.export_root)
                if saved_path:
                    try:
                        rel = saved_path.relative_to(cfg.vault_path)
                        routed["attachments"]["files"].append(str(rel))
                        routed["raw_dir"] = str(rel.parent)
                    except Exception:
                        routed["attachments"]["files"].append(str(saved_path))
                        routed["raw_dir"] = str(saved_path.parent)
                    routed["form"] = routed.get("form") or "video"
                    routed.setdefault("filenames", []).append(saved_path.name)
                    try:
                        # Используем семафор для ограничения параллельных ASR процессов
                        asr_sem = get_asr_semaphore()
                        async with asr_sem:
                            derived = await asyncio.to_thread(extract_from_path, str(saved_path))
                            import gc
                            gc.collect()
                        if derived.asr_text:
                            existing_asr = summary_obj["derived"].get("asr_text", "")
                            summary_obj["derived"]["asr_text"] = (existing_asr + "\n" + derived.asr_text).strip() if existing_asr else derived.asr_text
                        if derived.vision_text:
                            existing_vis = summary_obj["derived"].get("vision_text", "")
                            summary_obj["derived"]["vision_text"] = (existing_vis + "\n" + derived.vision_text).strip() if existing_vis else derived.vision_text
                    except Exception as _ee:
                        logging.getLogger("kb.bot").warning("asr after ytdlp failed: %s", _ee)
    except Exception as _e:
        logging.getLogger("kb.bot").warning("ytdlp fallback failed: %s", _e)
    
    # Финальный роутинг если type еще не установлен (после загрузки всех медиа)
    if not routed.get("type"):
        try:
            routed = route_and_fill(llm, summary_obj, source_hint="telegram")
            routed.setdefault("attachments", {"links": [], "files": []})
            log.info("Final routing: type=%s title=%s", routed.get("type"), routed.get("title"))
        except Exception as final_route_err:
            log.warning("Final routing failed: %s", final_route_err)
            routed.setdefault("type", "ссылка")  # Fallback

    # Naming: use summary context for robust 2–3 word title
    try:
        naming_system = load_prompt(cfg.agent_config_path, "naming")
        naming_input = json.dumps({
            "type": routed.get("type"),
            "summary": summary_obj,
            "filenames": routed.get("filenames", []),
            "hint_title": routed.get("title")
        }, ensure_ascii=False)
        named = llm.chat_json(naming_system, naming_input).content or {}
        # Проверяем, что named - это словарь и содержит только title (не весь routing объект)
        if isinstance(named, dict):
            title_val = named.get("title")
            # Если fallback вернул весь объект (с type, tags и т.д.), игнорируем его
            # Используем title только если:
            # 1. Это строка (не JSON объект)
            # 2. Не начинается с { (не JSON строка)
            # 3. Имеет разумную длину (не весь JSON dump)
            if isinstance(title_val, str) and title_val.strip():
                title_clean = title_val.strip()
                # Проверяем, что это не JSON строка или объект
                if not (title_clean.startswith("{") or title_clean.startswith("[")):
                    # Проверяем, что это не слишком длинная строка (вероятно JSON dump)
                    if len(title_clean) < 200:
                        routed["title"] = title_clean
    except Exception:
        pass
    routed.setdefault("title", "Без названия")
    # Если по ссылке пришёл мусорный заголовок страницы (например YouTube Terms Privacy), подставить название из oEmbed
    if yt_url:
        t = (routed.get("title") or "").strip()
        if t and ("youtube terms" in t.lower() or (len(t) < 25 and "privacy" in t.lower())):
            try:
                from knowledge_bot.services.extract.youtube import get_youtube_video_title
                fallback = await asyncio.to_thread(get_youtube_video_title, yt_url)
                if fallback:
                    routed["title"] = fallback
            except Exception:
                pass
    routed.setdefault("created", date.today().isoformat())
    # keep original raw text for insertion to note body
    routed.setdefault("raw_text", bundle.raw_text)
    # merge extracted URLs into attachments.links and capture Telegram entities with anchors
    try:
        import re
        def _normalize_url(u: str) -> str:
            return u.strip().strip(".,);]\'")

        links = set()
        anchors: dict[str, str] = {}
        # from routed (if any)
        for u in (routed.get("attachments", {}).get("links", []) or []):
            if isinstance(u, str) and u.startswith(("http://", "https://")):
                links.add(_normalize_url(u))
        # regex over raw text
        for m in re.finditer(r"https?://[^\s)]+", bundle.raw_text or ""):
            links.add(_normalize_url(m.group(0)))
        # telegram entities (text or caption) - обрабатываем все сообщения из группы
        for msg in all_messages:
            ents = msg.entities if msg.text is not None else msg.caption_entities
            txt = msg.text if msg.text is not None else (msg.caption or "")
            if ents:
                for ent in ents:
                    start = getattr(ent, "offset", 0)
                    length = getattr(ent, "length", 0)
                    piece = (txt or "")[start:start+length]
                    url_val = getattr(ent, "url", None) or piece
                    if isinstance(url_val, str) and url_val.startswith(("http://", "https://")):
                        nurl = _normalize_url(url_val)
                        links.add(nurl)
                        anchor_text = piece.strip()
                        if anchor_text and anchor_text != url_val:
                            anchors.setdefault(nurl, anchor_text)
        routed.setdefault("attachments", {"links": [], "files": []})
        routed["attachments"]["links"] = sorted(links)
        if anchors:
            routed["links_anchors"] = [{"url": u, "text": anchors[u]} for u in sorted(anchors.keys())]
    except Exception:
        pass

    # Fallback for heavy video via yt-dlp when Telegram refuses to download large files
    try:
        if os.environ.get("YTDLP_ENABLED", "0") == "1":
            has_files = bool((routed.get("attachments", {}) or {}).get("files"))
            ytdlp_url = None
            if not has_files:
                for u in routed.get("attachments", {}).get("links", []) or []:
                    if any(d in u for d in ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "x.com", "twitter.com")):
                        ytdlp_url = u
                        break
            if ytdlp_url:
                from knowledge_bot.services.extract.youtube import download_via_ytdlp
                saved_path = download_via_ytdlp(ytdlp_url, cfg.export_root)
                if saved_path:
                    try:
                        rel = saved_path.relative_to(cfg.vault_path)
                        routed["attachments"]["files"].append(str(rel))
                        routed["raw_dir"] = str(rel.parent)
                    except Exception:
                        routed["attachments"]["files"].append(str(saved_path))
                        routed["raw_dir"] = str(saved_path.parent)
                    routed["form"] = routed.get("form") or "video"
                    routed.setdefault("filenames", []).append(saved_path.name)
                    # Try ASR on downloaded media
                    try:
                        # Используем семафор для ограничения параллельных ASR процессов
                        asr_sem = get_asr_semaphore()
                        async with asr_sem:
                            derived = await asyncio.to_thread(extract_from_path, str(saved_path))
                            import gc
                            gc.collect()
                        if derived.asr_text:
                            summary_obj["derived"]["asr_text"] = derived.asr_text
                        if derived.vision_text:
                            summary_obj["derived"]["vision_text"] = derived.vision_text
                    except Exception as _ee:
                        logging.getLogger("kb.bot").warning("asr after ytdlp failed: %s", _ee)
    except Exception as _e:
        logging.getLogger("kb.bot").warning("ytdlp fallback failed: %s", _e)
    # Field fill: restrict to template fields
    try:
        enums_cfg = load_enums_config(cfg.agent_config_path)
        allowed_fields = allowed_fields_for_type(routed["type"]) or []
        field_system = load_prompt(cfg.agent_config_path, "field_fill")
        user = {
            "type": routed["type"],
            "allowed_fields": allowed_fields,
            "summary": summary_obj,
            "filenames": routed.get("filenames", []),
            "enums": {
                "namespaces_controlled": enums_cfg.namespaces_controlled,
                "common": enums_cfg.common,
                "per_type": enums_cfg.per_type,
            }
        }
        filled = llm.chat_json(field_system, json.dumps(user, ensure_ascii=False)).content or {}
        # Не перезаписывать производные поля (уже заполнены из медиа/YouTube), если значение не пустое
        derived_keys = {"yt_transcript_summary", "asr_text", "vision_text", "asr_summary"}
        for k in allowed_fields:
            if k in filled:
                if k in derived_keys and routed.get(k):
                    continue  # сохраняем уже заполненное из extract/LLM
                routed[k] = filled[k]
    except Exception as e:
        log.warning("field_fill failed: %s", e)

    # Tags step: generate from type, summary, attachments, enums, and filled fields
    try:
        enums_cfg = load_enums_config(cfg.agent_config_path)
        tags_system = load_prompt(cfg.agent_config_path, "tags")
        ctx = get_author_context(cfg.agent_config_path)
        author_line = f"Учти личность автора: {ctx}\n\n" if ctx else ""
        tags_system = tags_system.replace("{{AUTHOR_CONTEXT_LINE}}", author_line)
        # Add tags inventory to system prompt
        tags_inventory_text = get_tags_inventory_for_prompt(cfg.agent_config_path)
        domain_topic_path = cfg.agent_config_path.parent / "docs" / "DOMAIN_VS_TOPIC.md"
        domain_topic_block = ""
        if domain_topic_path.exists():
            domain_topic_block = "\n\n---\n" + domain_topic_path.read_text(encoding="utf-8")
        tags_system = f"{tags_system}\n\n{tags_inventory_text}{domain_topic_block}"
        # Collect fields that were filled and may impact tags
        fields_for_tags = {}
        for k, v in routed.items():
            if k not in {"type", "title", "created", "tags", "attachments", "source", "form", "raw_text", "raw_dir"}:
                fields_for_tags[k] = v
        tags_user = {
            "type": routed.get("type"),
            "summary": summary_obj,
            "attachments": {"links": routed.get("attachments", {}).get("links", [])},
            "enums": {
                "namespaces_controlled": enums_cfg.namespaces_controlled,
                "common": enums_cfg.common,
                "per_type": enums_cfg.per_type,
            },
            "synonyms": enums_cfg.synonyms,
            "filenames": routed.get("filenames", []),
            "fields": fields_for_tags,
        }
        tag_resp = llm.chat_json(tags_system, json.dumps(tags_user, ensure_ascii=False)).content or []
        # Normalize to list of strings
        if isinstance(tag_resp, dict) and "tags" in tag_resp:
            tag_candidates = tag_resp.get("tags") or []
        else:
            tag_candidates = tag_resp if isinstance(tag_resp, list) else []
        # Normalize tags to all-English ASCII slugs (free namespaces), lower-case namespaces
        def _translit_ru(s: str) -> str:
            table = str.maketrans({
                "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"i",
                "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
                "х":"h","ц":"c","ч":"ch","ш":"sh","щ":"shch","ы":"y","э":"e","ю":"yu","я":"ya",
                "А":"a","Б":"b","В":"v","Г":"g","Д":"d","Е":"e","Ё":"e","Ж":"zh","З":"z","И":"i","Й":"i",
                "К":"k","Л":"l","М":"m","Н":"n","О":"o","П":"p","Р":"r","С":"s","Т":"t","У":"u","Ф":"f",
                "Х":"h","Ц":"c","Ч":"ch","Ш":"sh","Щ":"shch","Ы":"y","Э":"e","Ю":"yu","Я":"ya",
            })
            return s.translate(table)

        def _slug_ascii(s: str) -> str:
            import re
            s = _translit_ru(s)
            s = s.lower()
            s = s.replace(" ", "-").replace("_", "-")
            s = re.sub(r"[^a-z0-9\-/]", "", s)
            s = re.sub(r"-+", "-", s).strip("-")
            return s

        tag_values = []
        for tag in tag_candidates:
            if isinstance(tag, str) and "/" in tag:
                ns, _, val = tag.strip().partition("/")
                ns = (ns or "").strip().lower()
                raw_val = (val or "").strip()
                # apply synonyms if provided for namespace (exact match, case-insensitive)
                syn_map = getattr(enums_cfg, "synonyms", {}).get(ns, {}) if 'enums_cfg' in locals() else {}
                mapped = syn_map.get(raw_val.lower())
                if mapped:
                    raw_val = mapped
                # candidate ascii slug
                cand_slug = _slug_ascii(raw_val)
                # if namespace is controlled (per config), try to map to allowed canonical values
                per_type_enums = enums_cfg.per_type.get(routed.get("type", ""), {})
                allowed_list = (enums_cfg.common.get(ns) or per_type_enums.get(ns)) or []
                is_controlled = ns in enums_cfg.namespaces_controlled
                if is_controlled and allowed_list:
                    # pick allowed value whose slug matches candidate
                    chosen = None
                    for allowed_val in allowed_list:
                        if _slug_ascii(str(allowed_val)) == cand_slug:
                            chosen = allowed_val
                            break
                    if chosen:
                        tag_values.append(f"{ns}/{chosen}")
                    else:
                        # no good match -> skip to avoid non-canonical values
                        continue
                else:
                    # free namespace
                    if ns and cand_slug:
                        tag_values.append(f"{ns}/{cand_slug}")
        # Filter controlled namespaces against enums
        filtered = []
        per_type_enums = enums_cfg.per_type.get(routed.get("type", ""), {})
        for tag in tag_values:
            ns, _, value = tag.partition("/")
            if ns in enums_cfg.namespaces_controlled:
                allowed = enums_cfg.common.get(ns) or per_type_enums.get(ns)
                if allowed and value in allowed:
                    filtered.append(tag)
            else:
                filtered.append(tag)
        routed["tags"] = sorted(dict.fromkeys(filtered))
    except Exception as e:
        logging.getLogger("kb.bot").warning("tags generation failed: %s", e)
        routed.setdefault("tags", [])

    # Передать в шаблон производные поля (описание сцены и т.д.)
    routed["vision_text"] = (summary_obj["derived"].get("vision_text") or "").strip()
    # Гарантированно подставить yt_transcript_summary в payload для рендера (для типа «видео»)
    if summary_obj["derived"].get("yt_transcript_summary") and not routed.get("yt_transcript_summary"):
        routed["yt_transcript_summary"] = summary_obj["derived"]["yt_transcript_summary"]
        log.info("[DEBUG yt] filled routed from derived, len=%d", len(routed["yt_transcript_summary"]))
    log.info("[DEBUG yt] before first render: type=%s, has_yt_in_routed=%s, yt_len=%s",
             routed.get("type"), "yt_transcript_summary" in routed and bool(routed.get("yt_transcript_summary")),
             len(routed.get("yt_transcript_summary") or ""))
    log.info("Rendering note and generating review...")
    try:
        rendered = render_note(cfg.templates_path, routed)
        if os.environ.get("ENABLE_WIKILINKS") == "1":
            rendered = inject_wikilinks(rendered, cfg.agent_config_path, cfg.vault_path, llm)
        log.info("Note rendered successfully")
    except Exception as render_err:
        log.error("Failed to render note: %s", render_err, exc_info=True)
        rendered = ""
    
    # Генерируем ревью заметки
    try:
        review_text = generate_note_review(routed, summary_obj)
        log.info("Review text generated (len=%d)", len(review_text))
    except Exception as review_err:
        log.error("Failed to generate review: %s", review_err, exc_info=True)
        review_text = f"Готово к сохранению — тип: {routed.get('type', 'не определен')}\nНазвание: {routed.get('title', 'Без названия')}"
    
    # Удаляем промежуточное сообщение "Обрабатываю..."
    if processing_msg:
        try:
            await processing_msg.delete()
            log.debug("Processing message deleted")
        except Exception:
            pass  # Не критично, если не удалось удалить
    
    # Экранируем спецсимволы Markdown для безопасности (если используется Markdown)
    # Убираем parse_mode, так как могут быть проблемы с парсингом
    # Telegram V2 API поддерживает HTML, но Markdown более чувствителен к ошибкам
    
    # Защита от дублирования: если для этого message_id уже отправляли ревью недавно (в течение 10 сек), пропускаем
    msg_id = main_message.message_id if main_message else None
    if msg_id and msg_id in app_state._RECENT_REVIEWS:
        elapsed = time.time() - app_state._RECENT_REVIEWS[msg_id]
        if elapsed < 10.0:
            log.warning("Skipping duplicate review for message_id=%d (sent %.1fs ago)", msg_id, elapsed)
            return
    
    # Send review and bind state to the preview message id to support multiple parallel drafts per user
    # Используем rate limiter и retry с экспоненциальным backoff
    log.info("Sending review message (len=%d, main_message=%s)...", len(review_text), main_message.message_id if main_message else "None")
    
    preview_msg = None
    max_retries = 5
    base_delay = 1.0
    
    async def _send_with_rate_limit(text: str, use_markup: bool = True) -> Message | None:
        """Отправляет сообщение с учетом rate limiting"""
        limiter = get_message_rate_limiter()
        async with limiter:
            # Увеличена задержка до 3 сек между сообщениями для стабильной обработки множества видео
            await asyncio.sleep(3.0)
            if use_markup:
                return await main_message.answer(
                    text[:4096],
                    reply_markup=preview_keyboard().as_markup(),
                )
            else:
                return await main_message.answer(text[:4096])
    
    # Retry логика с экспоненциальным backoff
    for attempt in range(max_retries):
        try:
            preview_msg = await _send_with_rate_limit(review_text[:4096], use_markup=True)
            log.info("Review message sent successfully (msg_id=%d, attempt=%d)", preview_msg.message_id if preview_msg else 0, attempt + 1)
            # Отмечаем, что ревью отправлено для этого message_id
            if msg_id:
                app_state._RECENT_REVIEWS[msg_id] = time.time()
                # Очищаем старые записи (старше 60 сек)
                stale = [k for k, v in list(app_state._RECENT_REVIEWS.items()) if time.time() - v >= 60.0]
                for k in stale:
                    app_state._RECENT_REVIEWS.pop(k, None)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Экспоненциальный backoff: 1s, 2s, 4s, 8s
                log.warning("Failed to send review message (attempt %d/%d): %s, retrying in %.1fs...", 
                           attempt + 1, max_retries, e, delay)
                await asyncio.sleep(delay)
            else:
                log.error("Failed to send review message after %d attempts: %s", max_retries, e, exc_info=True)
                # Пробуем без форматирования (последняя попытка)
                try:
                    preview_msg = await _send_with_rate_limit(
                        review_text[:4096].replace("*", "").replace("_", "").replace("`", ""),
                        use_markup=True
                    )
                    log.info("Review message sent (plain text, msg_id=%d)", preview_msg.message_id if preview_msg else 0)
                except Exception as e2:
                    log.error("Failed to send plain review message: %s", e2, exc_info=True)
                    # Последняя попытка - простой текст без markup
                    try:
                        preview_msg = await _send_with_rate_limit(
                            f"Готово к сохранению — тип: {routed['type']}\nНазвание: {routed['title']}",
                            use_markup=True
                        )
                        log.info("Review message sent (fallback, msg_id=%d)", preview_msg.message_id if preview_msg else 0)
                    except Exception as e3:
                        log.error("Failed to send fallback review message: %s", e3, exc_info=True)
                        return  # Не удалось отправить ответ
    
    if not preview_msg:
        log.error("Could not send review message after all retries, giving up")
        return
    log.info("[DEBUG yt] storing app_state._PENDING[%s]: payload has yt_transcript_summary=%s, len=%s",
             preview_msg.message_id, "yt_transcript_summary" in routed and bool(routed.get("yt_transcript_summary")),
             len(routed.get("yt_transcript_summary") or ""))
    app_state._PENDING[preview_msg.message_id] = {"payload": routed, "rendered": rendered, "summary": summary_obj}
    
    # Очищаем media_group после обработки
    if media_group_id:
        app_state._MEDIA_GROUPS[media_group_id]["processed"] = True
        app_state._MEDIA_GROUPS[media_group_id]["processing"] = False
        # Удаляем через некоторое время, чтобы не накапливать
        asyncio.create_task(cleanup_media_group_after_delay(media_group_id, delay=60))
    # Ограничиваем размер _PENDING и освобождаем память после тяжёлой обработки (снижение риска OOM)
    limit = pending_limit()
    if len(app_state._PENDING) > limit:
        by_id = sorted(app_state._PENDING.keys())
        for old_id in by_id[:-limit]:
            app_state._PENDING.pop(old_id, None)
        log.info("PENDING evicted oldest entries, kept last %d (limit=%d)", limit, limit)
    import gc
    gc.collect()
