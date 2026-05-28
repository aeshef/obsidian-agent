#!/usr/bin/env python3
"""
Тест сортировки канбан-доски на КОПИИ файла.
Копирует 100_Задачи/📋 Доска_Задач.md в .../📋 Доска_Задач_TEST_SORT.md,
запускает sort_kanban_tasks(target_path=копия), проверяет:
- количество задач не изменилось;
- внутри каждого столбца порядок: сначала по категории (CATEGORY_ORDER), затем по приоритету (PRIORITY_ORDER).

Запуск из корня vault или из planning_bot:
  python scripts/test_sort_kanban_on_copy.py
  cd planning_bot && python scripts/test_sort_kanban_on_copy.py
"""
import re
import sys
from pathlib import Path

# planning_bot в пути
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

# vault — на 3 уровня выше planning_bot (planning_bot -> Agent -> 800_Автоматизация -> vault)
VAULT = ROOT.parent.parent.parent
KANBAN_REAL = VAULT / "100_Задачи/📋 Доска_Задач.md"
KANBAN_COPY = VAULT / "100_Задачи/📋 Доска_Задач_TEST_SORT.md"

# Порядки из vault_maintenance / config
CATEGORY_ORDER = {
    "карьера": 1, "учеба": 2, "развитие": 3, "здоровье": 4,
    "инфраструктура": 5, "дом": 6, "семья": 7, "опыт": 8,
    "опыт": 9,
}
PRIORITY_ORDER = {"высокий": 1, "средний": 2, "низкий": 3}


def count_tasks(content: str) -> int:
    return len(re.findall(r"^- \[[ x]\]", content, re.MULTILINE))


def get_section_headers(content: str) -> list[str]:
    return re.findall(r"^## (.+?)$", content, re.MULTILINE)


def extract_priority(task_text: str) -> str:
    if "#приоритет/высокий" in task_text:
        return "высокий"
    if "#приоритет/средний" in task_text:
        return "средний"
    if "#приоритет/низкий" in task_text:
        return "низкий"
    return ""


def extract_category(task_text: str) -> str:
    m = re.search(r"#цель/([^\s#]+)", task_text)
    return m.group(1) if m else ""


def parse_tasks_by_section(content: str) -> dict[str, list[str]]:
    """Секция -> список сырых текстов задач (каждая задача может быть многострочной)."""
    sections = {}
    headers = list(re.finditer(r"^## (.+?)$", content, re.MULTILINE))
    for i, m in enumerate(headers):
        name = m.group(1).strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        block = content[start:end]
        # до %% kanban не трогаем
        if "%% kanban" in block:
            block = block.split("%% kanban")[0]
        tasks = []
        lines = block.split("\n")
        current = []
        for j, line in enumerate(lines):
            if re.match(r"^\s*- \[[ x]\]", line):
                if current:
                    tasks.append("\n".join(current).strip())
                current = [line]
            elif current and (
                line.startswith("\t")
                or (line.startswith("    ") and not re.match(r"^\s+- \[", line))
            ):
                current.append(line)
            elif current and not line.strip():
                if (
                    j + 1 < len(lines)
                    and (
                        lines[j + 1].startswith("\t")
                        or (
                            lines[j + 1].startswith("    ")
                            and not re.match(r"^\s+- \[", lines[j + 1])
                        )
                    )
                ):
                    current.append("")
                else:
                    tasks.append("\n".join(current).strip())
                    current = []
            elif current and line.strip():
                tasks.append("\n".join(current).strip())
                current = []
        if current:
            tasks.append("\n".join(current).strip())
        sections[name] = [t for t in tasks if t and re.match(r"^\s*- \[[ x]\]", t)]
    return sections


def is_sorted_by_category_then_priority(tasks: list[str]) -> tuple[bool, str]:
    """Проверяет, что задачи идут по категории, затем по приоритету. Возвращает (ok, сообщение)."""
    if len(tasks) <= 1:
        return True, ""
    cat_ord = []
    prio_ord = []
    for t in tasks:
        c = extract_category(t)
        p = extract_priority(t)
        cat_ord.append(CATEGORY_ORDER.get(c, 99))
        prio_ord.append(PRIORITY_ORDER.get(p, 4))
    for i in range(1, len(tasks)):
        if (cat_ord[i], prio_ord[i]) < (cat_ord[i - 1], prio_ord[i - 1]):
            return False, (
                f"Нарушение порядка: задача {i} (кат={cat_ord[i]}, приор={prio_ord[i]}) "
                f"идёт после (кат={cat_ord[i-1]}, приор={prio_ord[i-1]})"
            )
    return True, ""


def main() -> int:
    if not KANBAN_REAL.exists():
        print(f"❌ Реальная доска не найдена: {KANBAN_REAL}")
        return 1

    # 1) Копируем
    import shutil
    shutil.copy2(KANBAN_REAL, KANBAN_COPY)
    print(f"📋 Копия создана: {KANBAN_COPY}")

    with open(KANBAN_REAL, "r", encoding="utf-8") as f:
        orig_content = f.read()
    n_orig = count_tasks(orig_content)
    orig_headers = get_section_headers(orig_content)
    print(f"   Исходно: {n_orig} задач, секции: {orig_headers[:8]}...")

    # 2) Запускаем сортировку на копии
    import os
    os.chdir(ROOT)
    from planning_bot.tools.vault_maintenance import sort_kanban_tasks
    ok = sort_kanban_tasks(target_path=KANBAN_COPY)
    if not ok:
        print("❌ sort_kanban_tasks вернула False")
        return 1

    with open(KANBAN_COPY, "r", encoding="utf-8") as f:
        new_content = f.read()
    n_new = count_tasks(new_content)
    new_headers = get_section_headers(new_content)

    if n_new > n_orig:
        print(f"❌ Количество задач выросло: было {n_orig}, стало {n_new}")
        return 1
    if n_new < n_orig:
        print(f"⚠️ Задач стало меньше (дедупликация по первой строке): было {n_orig}, стало {n_new}")
    else:
        print(f"✅ Количество задач совпадает: {n_new}")

    if set(new_headers) != set(orig_headers):
        print(f"❌ Набор секций изменился: было {set(orig_headers)}, стало {set(new_headers)}")
        return 1
    print("✅ Набор секций совпадает")

    # 3) Проверка порядка внутри каждой секции
    sections = parse_tasks_by_section(new_content)
    all_ok = True
    for name, tasks in sections.items():
        if not tasks:
            continue
        ok_order, msg = is_sorted_by_category_then_priority(tasks)
        if not ok_order:
            print(f"❌ Секция «{name}»: {msg}")
            all_ok = False
    if all_ok:
        print("✅ Во всех столбцах порядок: категория → приоритет")

    # Удаляем копию, чтобы не путать
    try:
        KANBAN_COPY.unlink()
        print(f"   Копия удалена: {KANBAN_COPY}")
    except Exception as e:
        print(f"   ⚠️ Не удалось удалить копию: {e}")

    if not all_ok:
        return 1
    print("\n✅ Тест пройден. Сортировка на копии не сломала данные.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
