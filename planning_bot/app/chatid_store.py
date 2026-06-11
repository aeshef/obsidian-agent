"""Persist Telegram chat_id for scheduled messages."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

from planning_bot.core.pdmsg import pdmsg

logger = logging.getLogger(__name__)


def load_chat_id(chat_id_file: Path) -> Optional[int]:
    if chat_id_file.exists():
        try:
            with open(chat_id_file, encoding="utf-8") as f:
                content = f.read().strip()
                match = re.search(r"\d+", content)
                if match:
                    return int(match.group())
        except Exception:
            pass
    uid = (os.environ.get("TELEGRAM_USER_ID") or "").strip()
    if uid.isdigit():
        return int(uid)
    return None


def maybe_persist_chat_id(
    chat_id_file: Path,
    chat_id: int,
    *,
    current: int | None = None,
) -> int:
    """Update file when chat_id changes; return effective id."""
    if current != chat_id:
        save_chat_id(chat_id_file, chat_id)
    return chat_id

def save_chat_id(chat_id_file: Path, chat_id: int) -> None:
    try:
        chat_id_file.parent.mkdir(parents=True, exist_ok=True)
        with open(chat_id_file, "w", encoding="utf-8") as f:
            f.write(str(chat_id))
    except Exception as e:
        logger.debug(pdmsg("auto_eac0b04cb9"), chat_id_file, e)  # log