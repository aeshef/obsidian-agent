#!/usr/bin/env python3
"""One-off: strip Cyrillic from knowledge_bot runtime .py (comments -> English, strings -> domain_text)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CYR = re.compile(f"[{chr(0x400)}-{chr(0x4FF)}]")

# Whole-line comment replacements (exact match after strip)
COMMENT_MAP: dict[str, str] = {
    "# Голосовые и аудио: скачать, сохранить, ASR и использовать транскрипт для роутинга/названия": "# Voice/audio: download, save, ASR for routing/title",
    "# Пробуем через model_dump для aiogram 3.x": "# Try model_dump for aiogram 3.x",
    "# Логируем для отладки (INFO чтобы видеть в логах)": "# Debug logging for media messages",
    "# Это часть группы медиа": "# Part of a Telegram media group",
    "# Добавляем сообщение в группу": "# Append message to group buffer",
    "# Если группа уже обрабатывается или обработана - просто выходим": "# Skip if group already processing/processed",
    "# Только первое сообщение группы начинает обработку после ожидания": "# Only first message starts processing after wait",
    "# Остальные просто добавляются и выходят": "# Other messages only enqueue and return",
    "# Это не первое сообщение - просто выходим, обработка будет из первого": "# Not first message: defer to first handler",
    "# Это первое сообщение группы - ждем немного, чтобы собрать остальные": "# First message: wait to collect siblings",
    "# Проверяем еще раз, не началась ли обработка из другого потока (на всякий случай)": "# Re-check race after wait",
    "# Начинаем обработку": "# Start processing",
    "# Устанавливаем переменные для media_group": "# Bind media_group state",
    "# Используем семафор для ограничения параллельной обработки media_groups": "# Semaphore limits parallel media_group work",
    "# Это предотвратит одновременную обработку множества media_groups, что вызывает timeout": "# Avoid concurrent groups causing Telegram timeouts",
    "# Обычное сообщение": "# Single message (no group)",
}


def _english_comment(line: str) -> str | None:
    s = line.strip()
    if s in COMMENT_MAP:
        indent = line[: len(line) - len(line.lstrip())]
        return indent + COMMENT_MAP[s]
    if not s.startswith("#") or not _CYR.search(line):
        return None
    # Generic: drop Cyrillic-only explanatory comments
    if s.startswith("#") and len(s) < 120:
        return None
    return None


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        repl = _english_comment(line.rstrip("\n"))
        if repl is not None:
            out.append(repl + ("\n" if line.endswith("\n") else ""))
        else:
            out.append(line)
    text = "".join(out)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed = 0
    for rel in sys.argv[1:] or []:
        p = ROOT / rel
        if patch_file(p):
            changed += 1
            print("patched comments", rel)
    print("done", changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
