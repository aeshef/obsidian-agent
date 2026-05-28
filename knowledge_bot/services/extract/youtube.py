"""YouTube transcripts and media download."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
from datetime import date
from pathlib import Path
from typing import Optional

from knowledge_bot.services.extract._deps import requests, yt_dlp, yt_transcript_api

def _youtube_video_id(url: str) -> Optional[str]:
    """Extract helper."""
    u = (url or "").strip()
    if "youtube.com/watch" in u:
        m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", u)
        return m.group(1) if m else None
    if "youtu.be/" in u:
        m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", u)
        return m.group(1) if m else None
    if "youtube.com/embed/" in u:
        m = re.search(r"embed/([a-zA-Z0-9_-]{11})", u)
        return m.group(1) if m else None
    if "youtube.com/shorts/" in u:
        m = re.search(r"shorts/([a-zA-Z0-9_-]{11})", u)
        return m.group(1) if m else None
    return None


def get_youtube_video_title(url: str) -> Optional[str]:
    """Extract helper."""
    vid = _youtube_video_id(url)
    if not vid or not requests:
        return None
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
        r = requests.get(oembed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.ok:
            data = r.json()
            title = (data.get("title") or "").strip()
            if title and len(title) < 300:
                return title
    except Exception as e:
        log = logging.getLogger("kb.extract")
        log.debug("oEmbed title for %s failed: %s", vid, e)
    return None


def _parse_subtitle_file(path: Path) -> str:
    """Extract helper."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                continue
            if re.match(r"^\d{2}:\d{2}:\d{2}[\.,]\d+", line):
                continue
            if re.match(r"^\d+$", line):
                continue
            if " --> " in line:
                continue
            lines.append(line)
        return " ".join(lines)
    except Exception:
        return ""


_YT_PROXY_MISSING = object()

def _fetch_youtube_transcript_ytdlp(url: str, proxy: str | None = _YT_PROXY_MISSING) -> str:
    """Extract helper."""
    log = logging.getLogger("kb.extract")
    if not yt_dlp:
        return ""
    video_id = _youtube_video_id(url)
    if not video_id:
        return ""
    if proxy is _YT_PROXY_MISSING:
        proxy = os.environ.get("YOUTUBE_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    with tempfile.TemporaryDirectory(prefix="kb_yt_") as tmpdir:
        out_tmpl = str(Path(tmpdir) / "%(id)s")
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ru", "en", "ru.*", "en.*"],
            "subtitlesformat": "srt/vtt/best",
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
        }
        if proxy:
            opts["proxy"] = proxy
            log.info("YouTube transcript via yt-dlp with proxy for %s", video_id)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            for sub_path in list(Path(tmpdir).glob("*.srt")) + list(Path(tmpdir).glob("*.vtt")):
                result = _parse_subtitle_file(sub_path)
                if result and len(result) > 20:
                    log.info("YouTube transcript (yt-dlp): %d chars for %s", len(result), video_id)
                    return result
        except Exception as e:
            log.warning("yt-dlp transcript failed for %s: %s", video_id, e)
    return ""


def _fetch_youtube_transcript_api(video_id: str, proxy: str | None) -> str:
    """Extract helper."""
    log = logging.getLogger("kb.extract")
    if not yt_transcript_api:
        return ""
    try:
        proxy_config = None
        if proxy:
            try:
                from youtube_transcript_api.proxies import GenericProxyConfig
                proxy_config = GenericProxyConfig(https_url=proxy, http_url=proxy)
            except Exception as pe:
                log.warning("Proxy config failed: %s", pe)
        api = yt_transcript_api.YouTubeTranscriptApi(proxy_config=proxy_config)
        fetched = api.fetch(video_id, languages=("ru", "en"))
        if fetched and len(fetched) > 0:
            result = " ".join(s.text.strip() for s in fetched if getattr(s, "text", "").strip())
            if result:
                log.info("YouTube transcript (api): %d chars for %s", len(result), video_id)
                return result
    except Exception as e:
        log.warning("youtube-transcript-api failed for %s: %s", video_id, e)
    return ""


_yt_transcript_lock = None

def _get_yt_lock():
    global _yt_transcript_lock
    if _yt_transcript_lock is None:
        import threading
        _yt_transcript_lock = threading.Lock()
    return _yt_transcript_lock


def fetch_youtube_transcript(url: str) -> str:
    """Extract helper."""
    log = logging.getLogger("kb.extract")
    video_id = _youtube_video_id(url)
    if not video_id:
        return ""
    proxy = os.environ.get("YOUTUBE_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    def _try_both(use_proxy: str | None) -> str:
        result = _fetch_youtube_transcript_api(video_id, use_proxy)
        if result:
            return result
        if yt_dlp:
            result = _fetch_youtube_transcript_ytdlp(url, proxy=use_proxy)
            if result:
                return result
        return ""

    lock = _get_yt_lock()
    with lock:
        _pause = os.environ.get("YOUTUBE_TRANSCRIPT_PAUSE_SECONDS", "1")
        try:
            pause_sec = float(_pause)
            if pause_sec > 0:
                import time
                time.sleep(pause_sec)
        except ValueError:
            pass
        result = _try_both(proxy)
        if result:
            return result
        if proxy:
            log.info("YouTube transcript: retry without proxy for %s", video_id)
            result = _try_both(None)
    return result if result else ""


def download_via_ytdlp(url: str, export_root: Path) -> Optional[Path]:
    log = logging.getLogger("kb.extract")
    if yt_dlp is None:
        log.info("yt_dlp not installed; skip media download for %s", url)
        return None
    try:
        from datetime import date
        y = str(date.today().year)
        m = f"{date.today().month:02d}"
        out_dir = export_root / y / m
        out_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(out_dir / "%(id)s.%(ext)s")
        ydl_opts = {
            "outtmpl": outtmpl,
            "noprogress": True,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "format": os.environ.get("YTDLP_FORMAT", "mp4/bestaudio/best"),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Resolve final filename
            if info is None:
                return None
            if "requested_downloads" in info and info["requested_downloads"]:
                filename = info["requested_downloads"][0].get("filepath")
            else:
                filename = ydl.prepare_filename(info)
        path = Path(filename)
        log.info("yt_dlp downloaded: %s (%s)", path, url)
        return path if path.exists() else None
    except Exception as e:
        log.warning("yt_dlp failed for %s: %s", url, e)
        return None
