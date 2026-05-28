"""Persist Telegram chat_id for scheduled messages."""
from planning_bot.core.pdmsg import pdmsg
import logging
import re
from pathlib import Path
from typing import Optional
logger = logging.getLogger(__name__)

def load_chat_id(chat_id_file: Path) -> Optional[int]:
    if chat_id_file.exists():
        try:
            with open(chat_id_file, 'r') as f:
                content = f.read().strip()
                match = re.search('\\d+', content)
                if match:
                    return int(match.group())
        except Exception:
            pass
    return None

def save_chat_id(chat_id_file: Path, chat_id: int) -> None:
    try:
        chat_id_file.parent.mkdir(parents=True, exist_ok=True)
        with open(chat_id_file, 'w') as f:
            f.write(str(chat_id))
    except Exception as e:
        logger.debug(pdmsg("auto_eac0b04cb9"), chat_id_file, e)  # log