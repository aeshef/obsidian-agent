"""Vision analysis via OpenRouter for video frames."""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

from knowledge_bot.services.extract._deps import PIL, pytesseract, easyocr, requests
from knowledge_bot.services.extract.types import VisionRateLimitError

def _load_vision_prompt() -> str:
    from knowledge_bot.core.config import load_config
    from knowledge_bot.core.settings import load_prompt

    cfg = load_config()
    text = load_prompt(cfg.agent_config_path, "vision", required=True).strip()
    if not text:
        from knowledge_bot.i18n.domain_text import vision as vision_msg

        raise RuntimeError(vision_msg("empty_prompt"))
    return text


def _ffmpeg_timeout_sec() -> int:
    from shared.platform_timeouts import knowledge_ffmpeg_frame_timeout_sec

    return knowledge_ffmpeg_frame_timeout_sec()


def _ffprobe_timeout_sec() -> int:
    from shared.platform_timeouts import knowledge_ffprobe_timeout_sec

    return knowledge_ffprobe_timeout_sec()


def _extract_video_middle_frame(video_path: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Extract helper."""
    dur = _get_video_duration(video_path)
    t = dur / 2 if dur > 0 else 0
    tmpdir = Path(tempfile.mkdtemp(prefix="kb_video_ocr_"))
    out = tmpdir / "frame_mid.jpg"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(out)],
            capture_output=True,
            check=True,
            timeout=_ffmpeg_timeout_sec(),
        )
        if out.exists() and out.stat().st_size > 0:
            return out, tmpdir
    except Exception:
        pass
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass
    return None, None


def _get_video_duration(video_path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True,
            text=True,
            timeout=_ffprobe_timeout_sec(),
        )
        return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
    except Exception:
        return 0


def _extract_video_frames(video_path: Path, n: int = 5) -> Tuple[list[Path], Path]:
    """Extract helper."""
    dur = _get_video_duration(video_path)
    ts = [0] if dur <= 0 else [dur * i / max(n - 1, 1) for i in range(n)]
    tmpdir = Path(tempfile.mkdtemp(prefix="kb_video_"))
    frames = []
    for i, t in enumerate(ts):
        out = tmpdir / f"frame_{i:02d}.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(t), "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(out)],
                capture_output=True,
                check=True,
                timeout=_ffmpeg_timeout_sec(),
            )
            if out.exists() and out.stat().st_size > 0:
                frames.append(out)
        except subprocess.CalledProcessError:
            if not frames:
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(out)],
                        capture_output=True,
                        check=True,
                        timeout=_ffmpeg_timeout_sec(),
                    )
                    if out.exists() and out.stat().st_size > 0:
                        frames.append(out)
                except Exception:
                    pass
            break
        except Exception:
            break
    return frames, tmpdir


def _llm_asr_sufficient_to_skip_vision(llm_client: Optional[Any], asr_text: str) -> bool:
    """Ask LLM if ASR transcript is enough to skip Vision; False on error or missing client."""
    log = logging.getLogger("kb.extract")
    if not llm_client:
        return False
    t = (asr_text or "").strip()
    if len(t) < 25:
        return False
    try:
        from knowledge_bot.core.config import load_config
        from knowledge_bot.core.settings import load_prompt

        cfg = load_config()
        system = load_prompt(cfg.agent_config_path, "asr_skip_vision_gate")
        user = json.dumps({"transcript": t[:4500]}, ensure_ascii=False)
        model = os.environ.get("VISION_ASR_GATE_MODEL", "deepseek-chat")
        from shared.platform_timeouts import knowledge_vision_gate_timeout_sec

        result = llm_client.chat_json(
            system,
            user,
            model=model,
            timeout=knowledge_vision_gate_timeout_sec(),
            max_tokens=96,
        )
        payload = result.content if isinstance(result.content, dict) else {}
        val = payload.get("sufficient")
        if isinstance(val, bool):
            log.info("ASR vision gate: sufficient=%s", val)
            return val
        log.warning("ASR vision gate: unexpected JSON, running Vision")
        return False
    except Exception as e:
        log.warning("ASR vision gate failed: %s — running Vision", e)
        return False


def _vision_openrouter(images_b64: list[str], *, context_label: str) -> str:
    """Extract helper."""
    log = logging.getLogger("kb.extract")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not requests or not images_b64:
        log.info("Vision skip: OPENROUTER_API_KEY, requests or images missing")
        return ""
    model = os.environ.get("VISION_MODEL") or os.environ.get(
        "VISION_FALLBACK_MODEL", "google/gemini-2.5-flash"
    )
    base_url = "https://openrouter.ai/api/v1"
    from knowledge_bot.services.openrouter_rate_limit import openrouter_post
    from shared.platform_timeouts import (
        knowledge_vision_api_timeout_sec,
        knowledge_vision_openrouter_temperature,
    )

    content = [{"type": "text", "text": _load_vision_prompt()}]
    for b64 in images_b64:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 500,
        "temperature": knowledge_vision_openrouter_temperature(),
    }

    try:
        r = openrouter_post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/knowledge-bot",
            },
            json_payload=payload,
            timeout=knowledge_vision_api_timeout_sec(),
        )
        if r.ok:
            text = (r.json() or {}).get("choices", [{}])[0].get("message", {}).get("content", "")
            log.info(
                "Vision: %d chars from %d frame(s) (%s) for %s",
                len(text or ""),
                len(images_b64),
                model,
                context_label,
            )
            return (text or "").strip()
        from knowledge_bot.services.api_billing_alerts import send_billing_alert_if_needed

        send_billing_alert_if_needed("OpenRouter (Vision)", r.status_code, r.text or "")
        if r.status_code == 429:
            log.warning("Vision API 429 (rate limit after retry) — stopping batch")
            raise VisionRateLimitError("OpenRouter Vision rate limit (429)")
        log.warning("Vision API %s: %s", r.status_code, (r.text or "")[:200])
        return ""
    except VisionRateLimitError:
        raise
    except Exception as e:
        log.warning("Vision failed: %s", e)
        return ""


def extract_vision_from_image(path: Path) -> str:
    """Extract helper."""
    log = logging.getLogger("kb.extract")
    if not path.exists() or path.stat().st_size <= 0:
        return ""
    try:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return _vision_openrouter([b64], context_label=path.name)
    except Exception as e:
        log.warning("Vision image failed for %s: %s", path.name, e)
        return ""


def extract_vision_from_video(path: Path, asr_text: str = "", llm_client: Optional[Any] = None) -> str:
    """Extract helper."""
    log = logging.getLogger("kb.extract")
    if (
        os.environ.get("VISION_SKIP_IF_ASR_GOOD", "1") == "1"
        and asr_text
        and _llm_asr_sufficient_to_skip_vision(llm_client, asr_text)
    ):
        log.info("Vision skip: LLM says ASR sufficient (%d chars)", len(asr_text))
        return ""
    frames = []
    tmpdir = None
    try:
        frames, tmpdir = _extract_video_frames(path, n=5)
        if not frames:
            log.info("Vision: no frames extracted from %s", path.name)
            return ""
        images_b64 = [base64.b64encode(f.read_bytes()).decode("ascii") for f in frames]
        return _vision_openrouter(images_b64, context_label=path.name)
    except VisionRateLimitError:
        raise
    except Exception as e:
        log.warning("Vision extract failed: %s", e)
        return ""
    finally:
        if tmpdir and tmpdir.exists():
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
