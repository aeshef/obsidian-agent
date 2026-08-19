"""Daily random note reminder in Telegram (serendipity window + LLM pick)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import yaml
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from aiogram.types import FSInputFile

from shared.constants import deepseek_model
from shared.tz import get_tz

from knowledge_bot.core.config import AppConfig, load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.core.settings import load_prompt
from knowledge_bot.services.query.index_builder import build_or_refresh_index, load_index

log = logging.getLogger("kb.serendipity")

_KB_ROOT = Path(__file__).resolve().parent.parent


def _data_path(name: str) -> Path:
    p = _KB_ROOT / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / name


def _load_hit_stats() -> dict[str, int]:
    p = _data_path("note_hit_stats.json")
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items() if isinstance(v, (int, float))}
    return {}


def _tz():
    name = os.environ.get("SERENDIPITY_TZ") or os.environ.get("TIMEZONE")
    return get_tz(name)


def _last_sent_date(tz) -> date | None:
    p = _data_path("serendipity_last_date.txt")
    if not p.exists():
        return None
    try:
        s = p.read_text(encoding="utf-8").strip()[:10]
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _set_last_sent_date(tz) -> None:
    d = datetime.now(tz).date()
    _data_path("serendipity_last_date.txt").write_text(
        d.isoformat() + "\n", encoding="utf-8"
    )


def _window_hours() -> tuple[int, int]:
    """Hours from env override or push_policy (no hard-coded scenario clock)."""
    from shared.telegram import push_policy as pp

    env0 = (os.environ.get("SERENDIPITY_HOUR_START") or "").strip()
    env1 = (os.environ.get("SERENDIPITY_HOUR_END") or "").strip()
    h0 = int(env0) if env0.isdigit() else pp.serendipity_hour_start()
    h1 = int(env1) if env1.isdigit() else pp.serendipity_hour_end()
    return h0, h1


def _next_fire_at(tz) -> datetime:
    """Pick a random fire time inside the configured daytime window."""
    h0, h1 = _window_hours()
    if h1 <= h0:
        h1 = min(23, h0 + 4)
    now = datetime.now(tz)
    today = now.date()
    last = _last_sent_date(tz)
    for i in range(0, 14):
        d0 = today + timedelta(days=i)
        if last and last == d0:
            continue
        t_start = datetime.combine(d0, time(h0, 0, 0), tzinfo=tz)
        t_end = datetime.combine(d0, time(h1, 0, 0), tzinfo=tz)
        if t_end <= t_start:
            t_end = t_start + timedelta(hours=1)
        lo, hi = t_start, t_end
        if d0 == today:
            if now >= t_end:
                continue
            lo = max(t_start, now + timedelta(seconds=1))
        span = (hi - lo).total_seconds()
        if span < 5:
            continue
        r = random.uniform(0, max(1.0, span - 0.001))
        return lo + timedelta(seconds=r)
    return now + timedelta(hours=1)


def _candidate_entries(cfg: AppConfig) -> list[dict[str, Any]]:
    if os.environ.get("SERENDIPITY_REFRESH_INDEX", "").strip() in ("1", "true", "yes"):
        data = build_or_refresh_index(cfg.vault_path, force=False)
    else:
        data = load_index()
        if not (data.get("entries") or []):
            data = build_or_refresh_index(cfg.vault_path, force=True)
    entries: list[dict[str, Any]] = data.get("entries") or []
    video_only = os.environ.get("SERENDIPITY_VIDEO_ONLY", "1").strip() in (
        "1",
        "true",
        "yes",
    )
    if video_only:
        from knowledge_bot.i18n.domain_text import render as render_msg

        video_dir = render_msg("note_type_video")
        pool = [e for e in entries if f"/{video_dir}/" in (e.get("rel_path") or "")]
    else:
        from shared.vault_layout import knowledge_subdir

        kd = knowledge_subdir()
        pool = [e for e in entries if kd in (e.get("rel_path") or "")]
    if not pool and video_only:
        from shared.vault_layout import knowledge_subdir

        kd = knowledge_subdir()
        pool = [e for e in entries if kd in (e.get("rel_path") or "")]
    return pool


async def _pick_and_format(cfg: AppConfig) -> tuple[str, str] | None:
    pool = _candidate_entries(cfg)
    if not pool:
        log.warning("serendipity: no notes in index pool")
        return None
    n_cand = int(os.environ.get("SERENDIPITY_CANDIDATES", "45"))
    n_cand = max(5, min(n_cand, len(pool)))
    hits = _load_hit_stats()

    def w(e: dict) -> float:
        p = e.get("rel_path", "")
        h = int(hits.get(p, 0))
        return 1.0 / (1.0 + h) + 0.05

    weights = [w(e) for e in pool]
    picked: list[dict] = []
    rels: set[str] = set()
    for _ in range(n_cand * 3):
        e = random.choices(pool, weights=weights, k=1)[0]
        r = e.get("rel_path", "")
        if r and r not in rels:
            rels.add(r)
            picked.append(e)
        if len(picked) >= min(32, n_cand):
            break
    if len(picked) < 5:
        picked = random.sample(pool, min(30, len(pool)))

    user_payload = [
        {
            "p": e.get("rel_path", ""),
            "t": e.get("title", ""),
            "ty": e.get("type", ""),
            "tags": e.get("tags", []) or [],
        }
        for e in picked
    ]
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    if not llm or not (cfg.deepseek_api_key or "").strip():
        log.warning("serendipity: no DEEPSEEK / LLM, skip")
        return None
    from shared.platform_timeouts import knowledge_serendipity_timeout_sec

    system = load_prompt(cfg.agent_config_path, "serendipity_pick")
    model = deepseek_model(override=os.environ.get("SERENDIPITY_MODEL"))
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None,
        lambda: llm.chat_json(
            system,
            json.dumps(user_payload, ensure_ascii=False),
            model=str(model),
            timeout=knowledge_serendipity_timeout_sec(),
        ),
    )
    content = (res.content or {}) if res else {}
    if not isinstance(content, dict):
        return None
    rel = (content.get("rel_path") or content.get("rel") or "").strip()
    msg = (content.get("message") or "").strip()
    valid = {e.get("rel_path", "") for e in picked}
    if rel not in valid:
        # fallback: first candidate
        rel = picked[0].get("rel_path", "")
        if not rel:
            return None
    if not msg:
        t = next((e.get("title", "") for e in picked if e.get("rel_path") == rel), rel)
        from knowledge_bot.i18n.domain_text import serendipity as ser_msg

        msg = ser_msg("note_message", title=t, rel=rel)
    return rel, msg


def _line_with_path(message: str, rel_path: str) -> str:
    msg = (message or "").strip()
    if f"`{rel_path}`" in msg or rel_path in msg:
        return msg
    return f"{msg}\n\n`{rel_path}`"



def _safe_note_path(vault_path: Path, rel_path: str) -> Path | None:
    if not rel_path:
        return None
    p = (vault_path / rel_path).resolve()
    try:
        p.relative_to(vault_path.resolve())
    except ValueError:
        return None
    if not p.is_file():
        return None
    return p


def _parse_frontmatter_and_body(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---"):
        return {}, raw.strip()
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw.strip()
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, parts[2].strip()


def _extract_media_rel_paths(frontmatter: dict[str, Any]) -> list[str]:
    from knowledge_bot.services.frontmatter_attachments import attachment_files

    return attachment_files(frontmatter if isinstance(frontmatter, dict) else {})



async def _send_serendipity_text(bot, uid: int, body: str) -> bool:
    from shared.i18n import msg as i18n_msg
    from shared.telegram.push_format import format_push, send_push
    from shared.telegram import push_policy as pp

    if pp.in_quiet_hours(datetime.now(_tz())):
        log.info("serendipity: skip send — quiet hours")
        return False
    text = format_push(i18n_msg("push", "serendipity_title"), body)
    await send_push(bot, uid, text, disable_web_page_preview=True)
    return True


async def _send_serendipity_note_contents(bot, uid: int, cfg: AppConfig, rel: str, msg: str) -> bool:
    """Send styled serendipity push. Returns False if skipped (e.g. quiet hours)."""
    note_path = _safe_note_path(cfg.vault_path, rel)
    if not note_path:
        return await _send_serendipity_text(bot, uid, _line_with_path(msg, rel))

    try:
        raw = note_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return await _send_serendipity_text(bot, uid, _line_with_path(msg, rel))

    fm, _ = _parse_frontmatter_and_body(raw)
    title = str(fm.get("title") or note_path.stem).strip() or note_path.stem

    intro = (msg or "").strip()
    from knowledge_bot.i18n.domain_text import serendipity as ser_msg

    header = intro or ser_msg("header_fallback", title=title)
    if not await _send_serendipity_text(bot, uid, _line_with_path(header, rel)):
        return False

    media_files = _extract_media_rel_paths(fm)
    if not media_files:
        return True
    try:
        from shared.telegram.kb_media import send_vault_media_files

        await send_vault_media_files(
            bot,
            uid,
            cfg.vault_path,
            [(m, "") for m in media_files],
        )
    except Exception:
        log.warning("serendipity album send failed", exc_info=True)
        for media_rel in media_files:
            fp = _safe_note_path(cfg.vault_path, media_rel)
            if not fp:
                continue
            ext = fp.suffix.lower()
            try:
                media = FSInputFile(str(fp))
                if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
                    await bot.send_video(uid, media)
                elif ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    await bot.send_photo(uid, media)
                else:
                    await bot.send_document(uid, media)
            except Exception:
                log.warning("serendipity media send failed: %s", media_rel, exc_info=True)
    return True


async def serendipity_loop(bot) -> None:
    flag = (os.environ.get("SERENDIPITY_ENABLED", "") or "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        log.info("serendipity disabled (SERENDIPITY_ENABLED not set)")
        return
    from shared.telegram import push_policy as pp

    if not pp.serendipity_push_enabled():
        log.info("serendipity disabled (push_policy.serendipity.enabled=0)")
        return
    cfg = load_config()
    uid = cfg.telegram_user_id
    if not uid:
        log.warning("serendipity: TELEGRAM_USER_ID not set, skip")
        return
    tz = _tz()
    h0, h1 = _window_hours()
    log.info("serendipity loop: tz=%s window=%02d-%02d", tz, h0, h1)
    while True:
        try:
            target = _next_fire_at(tz)
            wait_s = (target - datetime.now(tz)).total_seconds()
            if wait_s < 0:
                wait_s = 60.0
            log.info("serendipity: next send at %s (%.0f s)", target.isoformat(), wait_s)
            await asyncio.sleep(min(max(wait_s, 1.0), 86400.0 * 2))
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("serendipity sleep")
            await asyncio.sleep(300)
            continue
        try:
            out = await _pick_and_format(cfg)
            if not out:
                continue
            rel, msg = out
            sent = await _send_serendipity_note_contents(bot, uid, cfg, rel, msg)
            if sent:
                _set_last_sent_date(tz)
        except Exception:
            log.exception("serendipity send failed")

def start_serendipity_task(bot) -> None:
    """Helper."""
    asyncio.create_task(serendipity_loop(bot))
