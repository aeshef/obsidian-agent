from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
import re
from typing import Dict, List, Optional, Tuple

_TASK_ID_HEX_RE = re.compile(r"^[0-9a-f]{6,8}$", re.IGNORECASE)


def is_substantive_task_text(
    text: str,
    *,
    min_alnum: int | None = None,
    min_words: int | None = None,
) -> bool:
    'Operation implementation.'
    from shared.agent.platform_config import platform_int

    alnum_limit = (
        min_alnum
        if min_alnum is not None
        else platform_int("planning", "task_min_alnum_chars", default=12)
    )
    word_limit = (
        min_words
        if min_words is not None
        else platform_int("planning", "task_min_words", default=4)
    )
    compact = re.sub(r"\s+", " ", (text or "").strip())
    alnum = sum(1 for c in compact if c.isalnum())
    words = [w for w in compact.split() if any(c.isalnum() for c in w)]
    return alnum >= alnum_limit and len(words) >= word_limit


def parse_task_blocks(section_body: str) -> List[str]:
    tasks: List[str] = []
    current: List[str] = []
    for line in section_body.split("\n"):
        if re.match(r"^\s*- \[[ x]\]", line):
            if current:
                block = "\n".join(current).strip()
                if block:
                    tasks.append(block)
            current = [line.rstrip()]
        elif current and (line.startswith("\t") or line.startswith("    ")):
            current.append(line.rstrip())
        elif current and not line.strip():
            continue
        elif current:
            block = "\n".join(current).strip()
            if block:
                tasks.append(block)
            current = []
    if current:
        block = "\n".join(current).strip()
        if block:
            tasks.append(block)
    return tasks


def parse_sections(content: str) -> Dict[str, List[str]]:
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    sections: Dict[str, List[str]] = {}
    section_pattern = r"^## ([^\n]+)\n\n(.*?)(?=\n## |\n%%|\Z)"
    for match in re.finditer(section_pattern, content, re.DOTALL | re.MULTILINE):
        col = match.group(1).strip()
        if not col:
            continue
        body = match.group(2)
        sections[col] = parse_task_blocks(body)
    return sections


def extract_id_from_block(block: str) -> Optional[str]:
    m = re.search(r"🆔 ID:\s*([0-9a-f]{6,8})\b", block, re.IGNORECASE)
    return m.group(1).lower() if m else None


def title_from_block(block: str) -> str:
    first = (block.split("\n") or [""])[0]
    m = re.match(r"^\s*- \[[ x]\]\s+(.+)", first)
    if not m:
        return ""
    return re.sub(r"\s*#.+", "", m.group(1)).strip()


def created_date_from_block(block: str) -> str:
    m = re.search(pdmsg("auto_04f3888a7d"), block)
    return m.group(1) if m else "0000-00-00"


def metadata_from_block(block: str) -> Dict[str, Optional[str]]:
    first = (block.split("\n") or [""])[0]
    is_completed = bool(re.match(r"^\s*- \[x\]", first))
    category = None
    priority = None
    deadline = None
    cm = re.search(pdmsg("auto_8d7e383ebe"), block)
    pm = re.search(pdmsg("auto_a1fb4d656a"), block)
    dm = re.search(pdmsg("auto_4f6bd2f69f"), block)
    if cm:
        category = cm.group(1)
    if pm:
        priority = pm.group(1)
    if dm:
        deadline = dm.group(1)
    return {
        "title": title_from_block(block),
        "completed": is_completed,
        "category": category,
        "priority": priority,
        "deadline": deadline,
        "created_date": created_date_from_block(block),
        "task_id": extract_id_from_block(block),
    }


def find_task_block(
    sections: Dict[str, List[str]], task_id: str
) -> Optional[Tuple[str, int, str]]:
    needle = (task_id or "").strip().lower()
    for col, tasks in sections.items():
        for i, block in enumerate(tasks):
            if extract_id_from_block(block) == needle:
                return col, i, block
    return None


def iter_tasks_with_columns(content: str):
    'Operation implementation.'
    for col, blocks in parse_sections(content).items():
        for block in blocks:
            yield col, block
