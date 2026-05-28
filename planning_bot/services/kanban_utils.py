from planning_bot.core.pdmsg import pdmsg
from typing import Optional, Tuple, List

from planning_bot.core.config import KANBAN_COLUMNS, BACKLOG_COLUMN


def get_column_by_position(content: str, task_position: int) -> str:
    'Operation implementation.'
    column_headers: List[Tuple[str, str]] = [
        (f"## {col}", col) for col in KANBAN_COLUMNS
    ] + [(pdmsg("auto_011aa6614f"), pdmsg("auto_ca7b1482d8"))]  # fallback alias

    last_column: Optional[str] = None
    last_position: int = -1

    for header, column_name in column_headers:
        header_pos = content.rfind(header, 0, task_position)
        if header_pos != -1 and header_pos > last_position:
            last_position = header_pos
            last_column = column_name

    return last_column or BACKLOG_COLUMN
