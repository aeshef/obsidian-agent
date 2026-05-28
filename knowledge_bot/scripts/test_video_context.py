#!/usr/bin/env python3
"""
Одноразовая проверка пайплайна видео: ASR + OCR кадра + Vision (OpenRouter).
Загружает knowledge_bot/.env из каталога скрипта.

Пример:
  python scripts/test_video_context.py "/path/to/video.mp4"
  TEST_VIDEO_PATH=/path/to/x.mp4 python scripts/test_video_context.py
  VISION_SKIP_IF_ASR_GOOD=0 python scripts/test_video_context.py /path/to/video.mp4   # всегда вызвать Vision
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Корень пакета: .../Agent
_AGENT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def _load_dotenv(env_path: Path) -> None:
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Уменьшить шум от библиотек
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    kb_dir = Path(__file__).resolve().parent.parent
    _load_dotenv(kb_dir / ".env")

    if len(sys.argv) > 1:
        video = Path(sys.argv[1]).expanduser()
    elif os.environ.get("TEST_VIDEO_PATH"):
        video = Path(os.environ["TEST_VIDEO_PATH"]).expanduser()
    else:
        print(
            "Укажи путь к видео: python scripts/test_video_context.py /path/to/file.mp4\n"
            "или задай TEST_VIDEO_PATH в окружении.",
            file=sys.stderr,
        )
        return 1
    if not video.is_file():
        print(f"Файл не найден: {video}", file=sys.stderr)
        return 1

    # Локальный vault: поднимаемся от файла, ищем каталог с 800_Автоматизация (игнорируем VAULT_PATH из .env сервера)
    v = video.resolve()
    for p in [v] + list(v.parents):
        if (p / "800_Автоматизация").is_dir():
            os.environ["VAULT_PATH"] = str(p)
            break
    # Чтобы в демо всегда увидеть вызов Vision (иначе при хорошем ASR может пропустить)
    os.environ.setdefault("VISION_SKIP_IF_ASR_GOOD", "0")

    from knowledge_bot.services.extract import extract_from_path

    print("=== test_video_context ===", flush=True)
    print(f"VIDEO: {video}", flush=True)
    print(f"VISION_MODEL={os.environ.get('VISION_MODEL', '(default in code)')}", flush=True)
    print(f"OPENROUTER_API_KEY={'set' if os.environ.get('OPENROUTER_API_KEY') else 'MISSING'}", flush=True)
    print(f"VISION_SKIP_IF_ASR_GOOD={os.environ.get('VISION_SKIP_IF_ASR_GOOD')}", flush=True)
    print(flush=True)

    bundle = extract_from_path(str(video))

    print("--- результат ExtractedBundle ---", flush=True)
    asr = (bundle.asr_text or "").strip()
    ocr = (bundle.ocr_text or "").strip()
    vis = (bundle.vision_text or "").strip()
    print(f"asr_text: {len(asr)} chars", flush=True)
    if asr:
        print(asr[:1200] + ("…" if len(asr) > 1200 else ""), flush=True)
    print(flush=True)
    print(f"ocr_text (middle frame): {len(ocr)} chars", flush=True)
    if ocr:
        print(ocr[:800] + ("…" if len(ocr) > 800 else ""), flush=True)
    print(flush=True)
    print(f"vision_text (OpenRouter): {len(vis)} chars", flush=True)
    if vis:
        print(vis[:1200] + ("…" if len(vis) > 1200 else ""), flush=True)
    print(flush=True)

    ok = bool(asr or ocr or vis)
    if not ok:
        print("Предупреждение: все три слоя пустые — проверь логи выше и сеть/OpenRouter.", flush=True)
        return 2
    print("OK: извлечение контекста отработало (хотя бы один слой не пустой).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
