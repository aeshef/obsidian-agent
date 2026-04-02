#!/usr/bin/env python3
import json
import re
from pathlib import Path

PAT = re.compile(
    r"## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\n\n\*\*Тип:\*\* (.+?)\n\n\*\*Данные:\*\*\n```json\n(.+?)\n```\n\n---\n\n",
    re.DOTALL,
)


def main() -> int:
    log_path = Path('/root/obsidian-vault/300_Дашборды/Логи/📊 Логи_Действий_2026-03.md')
    if not log_path.exists():
        print('log not found:', log_path)
        return 1

    content = log_path.read_text(encoding='utf-8', errors='replace')
    out = []
    seen = set()
    removed = 0
    removed_c2 = 0

    i = 0
    for m in PAT.finditer(content):
        if m.start() > i:
            out.append(content[i:m.start()])
        ts = m.group(1)
        typ = m.group(2).strip()
        data_raw = m.group(3)
        try:
            data = json.loads(data_raw)
        except Exception:
            out.append(m.group(0))
            i = m.end()
            continue

        key = (ts, typ, json.dumps(data, ensure_ascii=False, sort_keys=True))
        if key in seen:
            removed += 1
            if data.get('task_id') == 'c2ff889f':
                removed_c2 += 1
            i = m.end()
            continue

        seen.add(key)
        out.append(m.group(0))
        i = m.end()

    if i < len(content):
        out.append(content[i:])

    if removed == 0:
        print('No exact duplicates found; no changes')
        return 0

    bak = log_path.with_suffix(log_path.suffix + '.bak')
    bak.write_text(content, encoding='utf-8')
    log_path.write_text(''.join(out), encoding='utf-8')
    print('Removed exact duplicates:', removed, 'of which c2ff889f:', removed_c2)
    print('Backup:', bak)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
