"""Shared audio transcription.

Backends (configurable order):
  * HTTP — OpenAI-compatible ``/v1/audio/transcriptions`` (optional, via env);
  * ``faster_whisper`` (with optional model singleton cache);
  * ``whisper`` (with optional ffmpeg conversion to wav).

Defaults preserve planning/finance behavior (faster-whisper → whisper,
RuntimeError on failure). knowledge overrides order/options via parameters.
"""
from __future__ import annotations

import gc
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

from shared.domain_messages import dmsg
from shared.yaml_config import load_yaml


def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None


fwhisper = _safe_import("faster_whisper")
owhisper = _safe_import("whisper")
requests = _safe_import("requests")

# faster-whisper singleton: reused across calls,
# critical for batch load (knowledge), saves RAM and load time.
_fw_model = None
_fw_model_name: Optional[str] = None


def _resolve_languages(
    asr_cfg: Mapping[str, Any], lang_pref: Optional[Sequence[str]]
) -> List[str]:
    """Language list for forced attempts. ``auto``/empty → ['ru', 'en']."""
    if lang_pref:
        prefs = [p.strip() for p in lang_pref if p and p.strip()]
    else:
        prefs = list(asr_cfg.get("languages", ["ru", "en"]))
    forced = [p for p in prefs if p != "auto"]
    return forced or ["ru", "en"]


def _ffmpeg_extract_wav(src: Path, log: logging.Logger) -> Optional[Path]:
    """Convert audio to 16kHz mono wav (more stable for openai-whisper)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(wav_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return wav_path
    except Exception as e:
        log.warning("ffmpeg wav conversion failed: %s", e)
        return None


def _http_transcribe(
    path: Path, model_name: str, languages: Sequence[str], log: logging.Logger
) -> str:
    """ASR via OpenAI-compatible HTTP endpoint. Skipped for Ollama-base."""
    if requests is None:
        return ""
    try:
        base_url = (
            os.environ.get("ASR_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("OLLAMA_BASE_URL")
            or os.environ.get("EMBED_ENDPOINT")
        )
        api_key = (
            os.environ.get("ASR_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OLLAMA_API_KEY")
        )
        if not base_url or not api_key:
            return ""
        if "11434" in base_url or "ollama" in base_url.lower():
            log.info("ASR http skipped: Ollama base detected (%s)", base_url)
            return ""
        endpoint = os.environ.get("ASR_ENDPOINT", "/v1/audio/transcriptions")
        url = base_url.rstrip("/") + endpoint
        first_lang = next((l for l in languages if l != "auto"), None)
        data = {"model": model_name, "response_format": "json"}
        if first_lang:
            data["language"] = first_lang
        log.info("ASR http: url=%s model=%s", url, model_name)
        with open(path, "rb") as fh:
            files = {"file": (path.name, fh, "application/octet-stream")}
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files=files,
                timeout=600,
            )
        if resp.status_code == 200:
            j = resp.json()
            text = (j.get("text") if isinstance(j, dict) else "") or ""
            log.info("ASR done (http): len=%d", len(text))
            return text.strip()
        log.warning("ASR http failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:
        log.warning("ASR http exception: %s", e)
    return ""


def _faster_whisper_transcribe(
    path: Path,
    model_name: str,
    languages: Sequence[str],
    *,
    compute_type: str,
    vad_enabled: bool,
    vad_min_silence: int,
    min_text_length: int,
    use_singleton: bool,
    log: logging.Logger,
) -> str:
    if fwhisper is None:
        return ""
    global _fw_model, _fw_model_name
    best = ""
    try:
        if use_singleton:
            if _fw_model is None or _fw_model_name != model_name:
                if _fw_model is not None:
                    del _fw_model
                    gc.collect()
                log.info("Loading faster_whisper model: %s (may take time first run)", model_name)
                _fw_model = fwhisper.WhisperModel(model_name, compute_type=compute_type)
                _fw_model_name = model_name
            model = _fw_model
        else:
            model = fwhisper.WhisperModel(model_name, compute_type=compute_type)

        for lang in languages:
            for vad in (False, True) if vad_enabled else (False,):
                segments, info = model.transcribe(
                    str(path),
                    language=lang,
                    task="transcribe",
                    vad_filter=vad,
                    vad_parameters=dict(min_silence_duration_ms=vad_min_silence) if vad else None,
                )
                text = " ".join(
                    seg.text.strip() for seg in segments if getattr(seg, "text", "").strip()
                )
                log.info(
                    "ASR(fw) lang=%s vad=%s → len=%d detected=%s",
                    lang, vad, len(text or ""), getattr(info, "language", None),
                )
                if text:
                    t = text.strip()
                    if len(t) > len(best):
                        best = t
                    if len(t) >= min_text_length:
                        return t
    except Exception as e:
        log.warning("faster_whisper failed: %s", e)
    finally:
        if use_singleton:
            gc.collect()
    return best


def _whisper_transcribe(
    path: Path,
    model_name: str,
    languages: Sequence[str],
    *,
    convert_wav: bool,
    min_text_length: int,
    log: logging.Logger,
) -> str:
    if owhisper is None:
        return ""
    best = ""
    wav: Optional[Path] = None
    try:
        src = path
        if convert_wav:
            wav = _ffmpeg_extract_wav(path, log)
            if wav is not None:
                src = wav
        model = owhisper.load_model(model_name)
        for lang in languages:
            result = model.transcribe(str(src), language=lang, task="transcribe")
            text = (result or {}).get("text", "")
            log.info("ASR(whisper) lang=%s → len=%d", lang, len(text or ""))
            if text:
                t = text.strip()
                if len(t) > len(best):
                    best = t
                if len(t) >= min_text_length:
                    return t
    except Exception as e:
        log.warning("whisper failed: %s", e)
    finally:
        if wav is not None:
            try:
                wav.unlink()
            except Exception:
                pass
    return best


def transcribe_audio(
    path: Path,
    *,
    model_name: Optional[str] = None,
    asr_cfg: Optional[Mapping[str, Any]] = None,
    env_model: Optional[str] = None,
    log: Optional[logging.Logger] = None,
    raise_on_failure: bool = True,
    use_http: Optional[bool] = None,
    use_singleton: bool = False,
    backend_order: Sequence[str] = ("faster_whisper", "whisper"),
    convert_wav_for_whisper: bool = False,
    lang_pref: Optional[Sequence[str]] = None,
) -> str:
    """Transcribe audio (OGG/Opus from Telegram Voice etc.) to text.

    :param raise_on_failure: ``True`` (planning/finance) — RuntimeError on failure;
        ``False`` (knowledge, batch pipeline) — return empty string.
    :param use_http: ``None`` — auto (enabled when ASR/OpenAI base+key in env).
    :param use_singleton: cache faster-whisper model across calls.
    :param backend_order: local backend order.
    :param convert_wav_for_whisper: pre-convert to wav for whisper.
    :param lang_pref: language list (overrides ``asr_cfg['languages']``).
    """
    logger = log or logging.getLogger("shared.asr")
    cfg = dict(asr_cfg or {})

    model_name = (
        model_name
        or env_model
        or os.environ.get("ASR_MODEL")
        or cfg.get("default_model", "small")
    )
    languages = _resolve_languages(cfg, lang_pref)
    compute_type = cfg.get("compute_type", "int8")
    vad_cfg = cfg.get("vad") or {}
    vad_enabled = vad_cfg.get("enabled", True)
    vad_min_silence = vad_cfg.get("min_silence_duration_ms", 500)
    min_text_length = cfg.get("min_text_length", 10)

    logger.info("ASR start: model=%s langs=%s file=%s", model_name, ",".join(languages), path)

    best = ""

    def _consider(text: str, name: str) -> Optional[str]:
        nonlocal best
        if text:
            t = text.strip()
            if len(t) > len(best):
                best = t
            if len(t) >= min_text_length:
                logger.info("ASR done (%s): len=%d", name, len(t))
                return t
        return None

    if use_http is None:
        use_http = bool(
            os.environ.get("ASR_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("OLLAMA_BASE_URL")
        )
    if use_http:
        done = _consider(_http_transcribe(path, model_name, languages, logger), "http")
        if done is not None:
            return done

    for backend in backend_order:
        if backend == "faster_whisper":
            text = _faster_whisper_transcribe(
                path,
                model_name,
                languages,
                compute_type=compute_type,
                vad_enabled=vad_enabled,
                vad_min_silence=vad_min_silence,
                min_text_length=min_text_length,
                use_singleton=use_singleton,
                log=logger,
            )
        elif backend == "whisper":
            text = _whisper_transcribe(
                path,
                model_name,
                languages,
                convert_wav=convert_wav_for_whisper,
                min_text_length=min_text_length,
                log=logger,
            )
        else:
            logger.warning("ASR unknown backend: %s", backend)
            continue
        done = _consider(text, backend)
        if done is not None:
            return done

    if best:
        logger.info("ASR done (short result): len=%d", len(best))
        return best

    no_local = fwhisper is None and owhisper is None
    if no_local and not use_http:
        msg = dmsg("asr", "not_installed")
        if raise_on_failure:
            raise RuntimeError(msg)
        logger.warning(msg)
        return ""

    if raise_on_failure:
        raise RuntimeError(dmsg("asr", "recognition_failed"))
    logger.info("ASR unavailable; returning empty for %s", path)
    return ""


def transcribe_from_config(
    path: Path,
    config_dir: Path,
    *,
    model_name: Optional[str] = None,
    env_model: Optional[str] = None,
    log: Optional[logging.Logger] = None,
) -> str:
    """Transcription using asr_config.yaml(.example) from config_dir."""
    from shared.yaml_config import load_merged_config

    cfg = load_merged_config(str(config_dir), "asr_config")
    return transcribe_audio(
        path,
        model_name=model_name,
        asr_cfg=cfg,
        env_model=env_model,
        log=log,
    )
