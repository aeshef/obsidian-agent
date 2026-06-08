"""Numeric timeouts from config/agent/platform.yaml — no literals in prod callers."""
from __future__ import annotations

from shared.agent.platform_config import platform_float, platform_int


def asr_http_timeout_sec() -> float:
    return platform_float("asr", "http_timeout_sec", default=600.0)


def knowledge_text_intent_timeout_sec() -> float:
    return platform_float("knowledge_extract", "text_intent_timeout_sec", default=45.0)


def knowledge_vision_gate_timeout_sec() -> float:
    return platform_float("knowledge_extract", "vision_gate_timeout_sec", default=35.0)


def knowledge_vision_api_timeout_sec() -> float:
    return platform_float("knowledge_extract", "vision_api_timeout_sec", default=90.0)


def knowledge_ffmpeg_frame_timeout_sec() -> int:
    return platform_int("knowledge_extract", "ffmpeg_frame_timeout_sec", default=15)


def knowledge_ffprobe_timeout_sec() -> int:
    return platform_int("knowledge_extract", "ffprobe_timeout_sec", default=5)


def knowledge_web_fetch_timeout_sec() -> int:
    return platform_int("knowledge_extract", "web_fetch_timeout_sec", default=15)


def knowledge_serendipity_timeout_sec() -> float:
    return platform_float("knowledge_extract", "serendipity_timeout_sec", default=90.0)


def knowledge_vision_openrouter_temperature() -> float:
    return platform_float("knowledge_extract", "vision_openrouter_temperature", default=0.2)


def llm_reachable_timeout_sec() -> float:
    return platform_float("llm_reachable", "timeout_sec", default=4.0)
