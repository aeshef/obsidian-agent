#!/usr/bin/env python3
"""
Модуль для обслуживания vault: сортировка задач, синхронизация целей
Объединяет функциональность sort_kanban_tasks.py и sync_quarterly_focus.py
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = PROJECT_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

# Импортируем пути и константы из единого конфига (токены не требуются для скрипта)
from planning_bot.core.config import (
    VAULT_PATH, KANBAN_FILE, GOALS_FILE, QUARTERLY_FOCUS_FILE,
    CATEGORY_ORDER, PRIORITY_ORDER, LOGS_DIR, ACTION_LOGS_DIR,
    KANBAN_COLUMNS, DONE_COLUMN, GOALS_YEAR,
)


def sort_kanban_tasks(target_path: Optional[Path] = None) -> bool:
    """Сортировка задач в канбан-доске (внутри каждого статуса/колонки).
    Порядок: 1) с дедлайном (#дедлайн/YYYY-MM-DD) — сверху по ближайшей дате; 2) без дедлайна — по приоритету (высокий → средний → низкий). Категория не учитывается.
    target_path: если задан, сортировка читает и пишет этот файл (для теста на копии); иначе используется KANBAN_FILE.
    """
    path_to_use = (Path(target_path) if target_path else KANBAN_FILE).resolve()
    on_copy = target_path is not None
    
    print("🔄 Сортировка задач в канбан-доске..." + (" (тест на копии)" if on_copy else ""), flush=True)
    print(f"   Путь: {path_to_use}", flush=True)
    if not path_to_use.exists():
        print(f"❌ Файл {path_to_use} не найден!")
        return False
    
    # Сохраняем timestamp файла при чтении
    file_mtime = path_to_use.stat().st_mtime
    initial_mtime = file_mtime
    
    if not on_copy:
        time.sleep(0.2)
    
    # Читаем файл
    with open(path_to_use, 'r', encoding='utf-8') as f:
        content = f.read()
    # Нормализуем переносы строк (иначе при \r\n регекс ^## не находит секции и structure_broken = True)
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # ИСКЛЮЧЕНИЕ: Если структура файла сломана (только одна секция) или все задачи в одной колонке
    # Проверяем количество секций ПЕРЕД проверкой времени модификации
    section_count = len(re.findall(r'^## ', content, re.MULTILINE))
    
    # Также проверяем, все ли задачи в одной колонке (даже если секций несколько)
    # Считаем задачи в каждой секции
    tasks_per_section = {}
    for match in re.finditer(r'^## (.+?)$', content, re.MULTILINE):
        section_name = match.group(1).strip()
        # Считаем задачи в этой секции
        section_start = match.end()
        # Находим следующую секцию или конец
        next_match = re.search(r'^## ', content[section_start:], re.MULTILINE)
        if next_match:
            section_end = section_start + next_match.start()
        else:
            section_end = len(content)
        section_content = content[section_start:section_end]
        task_count = len(re.findall(r'^- \[[ x]\]', section_content))
        if task_count > 0:
            tasks_per_section[section_name] = task_count
    
    # Сломанной считаем только случай «одна секция» — иначе рискуем схлопнуть нормальную доску
    # (при пустом tasks_per_section из-за формата строк парсим доску построчно в else-ветке)
    structure_broken = section_count <= 1
    
    # КРИТИЧЕСКАЯ ЗАЩИТА: Проверяем, не был ли файл изменен недавно (в последние 5 минут)
    # Это предотвращает потерю изменений, если скрипт запускается сразу после синхронизации или редактирования
    # НО: если структура сломана, всегда разрешаем сортировку для восстановления
    current_time = time.time()
    time_since_modification = current_time - file_mtime
    
    # КРИТИЧЕСКАЯ ЗАЩИТА: только для прод-файла (не для копии при тесте).
    # FROM_SYNC=1: запуск из obsidian_sync.sh сразу после push — файл только что обновлён rsync,
    # защита бы всегда срабатывала и сортировка никогда не выполнялась; пропускаем проверку.
    from_sync = os.environ.get("FROM_SYNC") in ("1", "true", "yes")
    PROTECTION_WINDOW = 300  # 5 минут
    if not on_copy and not from_sync and time_since_modification < PROTECTION_WINDOW and not structure_broken:
        print(f"⚠️ Файл был изменен {time_since_modification:.1f} секунд назад (менее {PROTECTION_WINDOW} секунд)")
        print("⚠️ Пропускаем сортировку, чтобы не потерять недавние изменения пользователя")
        print("⚠️ Рекомендуется запустить скрипт позже, когда файл не будет редактироваться")
        return False
    
    if structure_broken:
        print("⚠️ Обнаружена сломанная структура файла (только одна секция), восстанавливаем...")
        # Если структура сломана, распределяем задачи по колонкам на основе их статуса
        # Сначала извлекаем все задачи из единственной секции
        all_tasks = []
        task_pattern = r'(- \[[ x]\]\s+.+?)(?=\n- \[|\n## |\n%%|$)'
        for match in re.finditer(task_pattern, content, re.DOTALL):
            task_text = match.group(1).strip()
            if task_text:
                all_tasks.append(task_text)
        
        # Распределяем задачи по колонкам (порядок как в KANBAN_COLUMNS)
        sections = {col: [] for col in KANBAN_COLUMNS}
        for task_text in all_tasks:
            if re.match(r'^\s*- \[x\]', task_text):
                sections[DONE_COLUMN].append(task_text)
            else:
                sections[KANBAN_COLUMNS[0]].append(task_text)
        
        # Переходим к сортировке (задачи уже распределены, пропускаем парсинг секций)
    else:
        sections = {}
        # Разбиваем на секции по заголовкам ## (только если структура не была сломана)
        # Используем более надежный паттерн: ищем все заголовки ## и затем содержимое до следующего заголовка
        section_headers = list(re.finditer(r'^## (.+?)$', content, re.MULTILINE))
        
        for i, header_match in enumerate(section_headers):
            section_name = header_match.group(1).strip()
            header_start = header_match.end()
            
            # Определяем конец секции: следующий заголовок ## или начало %% kanban:settings
            if i + 1 < len(section_headers):
                section_end = section_headers[i + 1].start()
            else:
                settings_match = re.search(r'%% kanban:settings', content[header_start:])
                if settings_match:
                    section_end = header_start + settings_match.start()
                else:
                    section_end = len(content)
            
            section_content = content[header_start:section_end].strip()
            
            # ИГНОРИРУЕМ содержимое, которое содержит заголовки ## (это поврежденный файл)
            # Если содержимое содержит "## ", значит файл поврежден и нужно пропустить эту секцию
            if '## ' in section_content:
                # Пытаемся извлечь только то, что до первого заголовка
                first_header_in_content = section_content.find('## ')
                if first_header_in_content > 0:
                    section_content = section_content[:first_header_in_content].strip()
                else:
                    # Секция полностью повреждена, пропускаем
                    continue
            
            # Парсим задачи из секции
            tasks = []
            lines = section_content.split('\n')
            current_task = []
            
            for j, line in enumerate(lines):
                # Начало новой задачи
                if re.match(r'^\s*- \[[ x]\]', line):
                    # Сохраняем предыдущую задачу
                    if current_task:
                        task_text = '\n'.join(current_task).strip()
                        if task_text and task_text not in tasks:
                            tasks.append(task_text)
                    current_task = [line]
                # Продолжение задачи (отступы)
                elif current_task and (line.startswith('\t') or (line.startswith('    ') and not re.match(r'^\s+- \[', line))):
                    current_task.append(line)
                # Пустая строка
                elif current_task and not line.strip():
                    if j + 1 < len(lines) and (lines[j+1].startswith('\t') or (lines[j+1].startswith('    ') and not re.match(r'^\s+- \[', lines[j+1]))):
                        current_task.append('')
                    else:
                        if current_task:
                            task_text = '\n'.join(current_task).strip()
                            if task_text and task_text not in tasks:
                                tasks.append(task_text)
                        current_task = []
                elif current_task and line.strip():
                    if current_task:
                        task_text = '\n'.join(current_task).strip()
                        if task_text and task_text not in tasks:
                            tasks.append(task_text)
                    current_task = []
            
            # Сохраняем последнюю задачу
            if current_task:
                task_text = '\n'.join(current_task).strip()
                if task_text and task_text not in tasks:
                    tasks.append(task_text)
            
            # ИСПРАВЛЕНИЕ: Если секция с таким именем уже существует, ОБЪЕДИНЯЕМ задачи
            if section_name in sections:
                existing_tasks = sections[section_name]
                existing_task_texts = set(task.strip() for task in existing_tasks)
                for task in tasks:
                    task_text = task.strip()
                    if task_text and task_text not in existing_task_texts:
                        existing_tasks.append(task)
                sections[section_name] = existing_tasks
            else:
                sections[section_name] = tasks
    # Конец блока парсинга секций (если структура не была сломана)
    
    def extract_priority(task_text: str) -> str:
        """Извлекает приоритет из текста задачи"""
        if "#приоритет/высокий" in task_text:
            return "высокий"
        elif "#приоритет/средний" in task_text:
            return "средний"
        elif "#приоритет/низкий" in task_text:
            return "низкий"
        return ""

    # Большое число для задач без даты дедлайна (чтобы они шли после задач с дедлайном)
    _NO_DEADLINE_ORDINAL = 9999999

    def extract_deadline_ordinal(task_text: str) -> Optional[int]:
        """Извлекает дату дедлайна (#дедлайн/YYYY-MM-DD) и возвращает toordinal() или None."""
        match = re.search(r"#дедлайн/(\d{4}-\d{2}-\d{2})", task_text)
        if not match:
            return None
        try:
            from datetime import datetime
            dt = datetime.strptime(match.group(1), "%Y-%m-%d")
            return dt.toordinal()
        except ValueError:
            return None
    
    def sort_key(task_text: str) -> Tuple[int, int, int, str]:
        """Ключ сортировки: 1) с дедлайном — сверху по ближайшей дате; 2) без дедлайна — по приоритету (высокий → низкий). Без привязки к категории."""
        deadline_ord = extract_deadline_ordinal(task_text)
        priority = extract_priority(task_text)
        pri_order = PRIORITY_ORDER.get(priority, 99)

        if deadline_ord is not None:
            # С дедлайном: сначала по дате (ближайшие сверху), затем по приоритету
            return (0, deadline_ord, pri_order, task_text.lower())
        # Без дедлайна: после всех с дедлайном, сортировка по приоритету (высокий → низкий)
        return (1, _NO_DEADLINE_ORDINAL, pri_order, task_text.lower())
    
    def sort_tasks_in_section(tasks: List[str]) -> List[str]:
        """Сортирует задачи в секции и убирает дубликаты"""
        unique_tasks = []
        seen = set()
        for task in tasks:
            first_line = task.split('\n')[0].strip()
            if first_line not in seen:
                seen.add(first_line)
                unique_tasks.append(task)
        
        return sorted(unique_tasks, key=lambda t: sort_key(t))
    
    # ИСПРАВЛЕНИЕ: Перемещаем выполненные задачи ([x]) в колонку "✅ Сделано"
    # независимо от того, в какой колонке они находятся
    done_tasks = []
    other_sections = {}
    
    for section_name, tasks in sections.items():
        if section_name == DONE_COLUMN:
            # Уже в правильной колонке, оставляем как есть
            other_sections[section_name] = tasks
            continue
        
        # Проверяем каждую задачу в секции
        remaining_tasks = []
        for task in tasks:
            # Если задача выполнена ([x]), перемещаем в "✅ Сделано"
            if re.match(r'^\s*- \[x\]', task):
                done_tasks.append(task)
            else:
                remaining_tasks.append(task)
        
        if remaining_tasks:
            other_sections[section_name] = remaining_tasks
    
    # Добавляем выполненные задачи в колонку «Сделано»
    if DONE_COLUMN not in other_sections:
        other_sections[DONE_COLUMN] = []
    other_sections[DONE_COLUMN].extend(done_tasks)
    
    sections = other_sections
    
    # Подсчитываем задачи
    total_before = sum(len(tasks) for tasks in sections.values())
    
    # Логируем количество задач по колонкам для отладки
    print(f"📊 Найдено задач по колонкам:")
    for section_name, tasks in sections.items():
        print(f"  {section_name}: {len(tasks)} задач")
    
    # Дедупликация и сортировка
    unique_sections = {}
    total_after = 0
    for section_name, tasks in sections.items():
        unique_tasks = sort_tasks_in_section(tasks)
        unique_sections[section_name] = unique_tasks
        total_after += len(unique_tasks)
        if len(unique_tasks) != len(tasks):
            print(f"  ⚠️ {section_name}: {len(tasks)} → {len(unique_tasks)} (после дедупликации)")
    
    if total_before != total_after:
        print(f"⚠️ Всего найдено {total_before} задач, после дедупликации: {total_after}")
    else:
        print(f"✅ Всего найдено {total_after} задач в {len(sections)} колонках")
    
    # Пересобираем файл
    header_match = re.search(r'^---\s*\n\s*kanban-plugin: board\s*\n---\s*\n', content, re.MULTILINE)
    if header_match:
        header = content[:header_match.end()]
    else:
        header = "---\n\nkanban-plugin: board\n\n---\n\n"
    
    settings_match = re.search(r'%% kanban:settings', content)
    if settings_match:
        footer = content[settings_match.start():]
    else:
        footer = "\n\n%% kanban:settings\n```\n{\"kanban-plugin\":\"board\"}\n```\n%%\n"
    
    new_content = header
    
    # Порядок колонок из конфига
    column_order = KANBAN_COLUMNS
    # Добавляем колонки в правильном порядке (всегда, даже если пустые)
    for section_name in column_order:
        new_content += f"## {section_name}\n\n"
        if section_name in unique_sections:
            sorted_tasks = unique_sections[section_name]
            for task in sorted_tasks:
                new_content += task + "\n\n"
        else:
            new_content += "\n"
    
    # Добавляем остальные секции (если есть)
    for section_name, tasks in unique_sections.items():
        if section_name not in column_order:
            new_content += f"## {section_name}\n\n"
            for task in tasks:
                new_content += task + "\n\n"
    
    new_content += "\n" + footer
    
    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Проверяем, не изменился ли файл после чтения
    # Если файл изменился, значит пользователь внес изменения, и мы не должны их перезаписывать
    # Делаем несколько проверок с задержками для надежности
    for check_attempt in range(3):
        if not on_copy:
            time.sleep(0.2)
        current_mtime = path_to_use.stat().st_mtime
        if current_mtime != initial_mtime:
            if check_attempt < 2:  # Еще есть попытки
                print(f"⚠️ Файл изменился (попытка {check_attempt + 1}/3), ждем стабилизации...")
                time.sleep(0.5)  # Дополнительная задержка
                continue
            else:
                # Файл действительно изменился
                break
        else:
            # Файл не изменился, можно продолжать
            break
    else:
        # Файл не изменился после всех проверок
        current_mtime = initial_mtime
    
    if current_mtime != initial_mtime and not on_copy:
        print(f"⚠️ Файл был изменен после чтения (timestamp изменился с {initial_mtime} на {current_mtime})")
        print("⚠️ Перечитываем файл и пересобираем структуру...")
        
        with open(path_to_use, 'r', encoding='utf-8') as f:
            current_content = f.read()
        
        # Пересобираем структуру на основе актуальной версии файла
        # Используем ту же логику парсинга, что и выше
        current_sections = {}
        current_section_headers = list(re.finditer(r'^## (.+?)$', current_content, re.MULTILINE))
        
        for i, header_match in enumerate(current_section_headers):
            section_name = header_match.group(1).strip()
            header_start = header_match.end()
            
            if i + 1 < len(current_section_headers):
                section_end = current_section_headers[i + 1].start()
            else:
                settings_match = re.search(r'%% kanban:settings', current_content[header_start:])
                if settings_match:
                    section_end = header_start + settings_match.start()
                else:
                    section_end = len(current_content)
            
            section_content = current_content[header_start:section_end].strip()
            
            # Пропускаем поврежденные секции
            if '## ' in section_content:
                first_header_in_content = section_content.find('## ')
                if first_header_in_content > 0:
                    section_content = section_content[:first_header_in_content].strip()
                else:
                    continue
            
            # Парсим задачи из секции
            tasks = []
            lines = section_content.split('\n')
            current_task = []
            
            for j, line in enumerate(lines):
                if re.match(r'^\s*- \[[ x]\]', line):
                    if current_task:
                        task_text = '\n'.join(current_task).strip()
                        if task_text and task_text not in tasks:
                            tasks.append(task_text)
                    current_task = [line]
                elif current_task and (line.startswith('\t') or (line.startswith('    ') and not re.match(r'^\s+- \[', line))):
                    current_task.append(line)
                elif current_task and not line.strip():
                    if j + 1 < len(lines) and (lines[j+1].startswith('\t') or (lines[j+1].startswith('    ') and not re.match(r'^\s+- \[', lines[j+1]))):
                        current_task.append('')
                    else:
                        if current_task:
                            task_text = '\n'.join(current_task).strip()
                            if task_text and task_text not in tasks:
                                tasks.append(task_text)
                        current_task = []
                elif current_task and line.strip():
                    if current_task:
                        task_text = '\n'.join(current_task).strip()
                        if task_text and task_text not in tasks:
                            tasks.append(task_text)
                    current_task = []
            
            if current_task:
                task_text = '\n'.join(current_task).strip()
                if task_text and task_text not in tasks:
                    tasks.append(task_text)
            
            # Объединяем с уже существующими задачами
            if section_name in current_sections:
                existing_tasks = current_sections[section_name]
                existing_task_texts = set(task.strip() for task in existing_tasks)
                for task in tasks:
                    task_text = task.strip()
                    if task_text and task_text not in existing_task_texts:
                        existing_tasks.append(task)
                current_sections[section_name] = existing_tasks
            else:
                current_sections[section_name] = tasks
        
        # Теперь применяем сортировку к актуальной версии
        sorted_sections = {}
        for section_name, tasks in current_sections.items():
            sorted_tasks = sort_tasks_in_section(tasks)
            sorted_sections[section_name] = sorted_tasks
        
        # Пересобираем файл на основе актуальной версии
        current_header_match = re.search(r'^---\s*\n\s*kanban-plugin: board\s*\n---\s*\n', current_content, re.MULTILINE)
        if current_header_match:
            current_header = current_content[:current_header_match.end()]
        else:
            current_header = "---\n\nkanban-plugin: board\n\n---\n\n"
        
        current_settings_match = re.search(r'%% kanban:settings', current_content)
        if current_settings_match:
            current_footer = current_content[current_settings_match.start():]
        else:
            current_footer = "\n\n%% kanban:settings\n```\n{\"kanban-plugin\":\"board\"}\n```\n%%\n"
        
        new_content = current_header
        
        # Добавляем колонки в правильном порядке
        for section_name in column_order:
            new_content += f"## {section_name}\n\n"
            if section_name in sorted_sections:
                sorted_tasks = sorted_sections[section_name]
                for task in sorted_tasks:
                    new_content += task + "\n\n"
            else:
                new_content += "\n"
        
        # Добавляем остальные секции
        for section_name, tasks in sorted_sections.items():
            if section_name not in column_order:
                new_content += f"## {section_name}\n\n"
                for task in tasks:
                    new_content += task + "\n\n"
        
        new_content += "\n" + current_footer
        
        # При запуске из синка (FROM_SYNC=1) всегда пишем: файл только что прилетел по rsync, конкурирующих правок нет
        from_sync = os.environ.get("FROM_SYNC") in ("1", "true", "yes")
        if not on_copy and not from_sync:
            for final_check in range(3):
                time.sleep(0.2)
                final_mtime = path_to_use.stat().st_mtime
                if final_mtime != current_mtime:
                    if final_check < 2:
                        print(f"⚠️ Файл изменился снова (проверка {final_check + 1}/3), ждем...")
                        time.sleep(0.5)
                        continue
                    else:
                        print(f"⚠️ Файл изменился снова во время обработки! Пропускаем запись.")
                        return False
                else:
                    break
    
    with open(path_to_use, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Канбан-доска отсортирована!")
    return True


def sync_quarterly_focus() -> bool:
    """Синхронизация целей из годового файла в квартальные фокусы"""
    print("🔄 Синхронизация квартальных фокусов...")
    
    if not GOALS_FILE.exists():
        print(f"⚠️ Файл {GOALS_FILE} не найден, пропускаю")
        return True
    
    with open(GOALS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    goals_by_quarter: Dict[str, List[Tuple[str, bool]]] = {
        'Q1': [],
        'Q2': [],
        'Q3': [],
        'Q4': [],
        'deadlines': []
    }
    
    # Ищем все задачи с тегами фокуса
    task_pattern = r'- \[([ x])\] (.+?)(?=\n- \[|$)'
    tasks = re.findall(task_pattern, content, re.MULTILINE | re.DOTALL)
    
    for checked, task_text in tasks:
        is_completed = checked.strip() == 'x'
        
        # Проверяем дедлайны
        if '#дедлайн' in task_text:
            goal_text = re.sub(r'#дедлайн/Q\d+\s*', '', task_text).strip()
            goals_by_quarter['deadlines'].append((goal_text, is_completed))
        
        # Проверяем фокус по кварталам
        for quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
            if f'#фокус/{quarter}' in task_text:
                goal_text = re.sub(r'#фокус/Q\d+\s*', '', task_text).strip()
                goals_by_quarter[quarter].append((goal_text, is_completed))
    
    if not QUARTERLY_FOCUS_FILE.exists():
        print(f"⚠️ Файл {QUARTERLY_FOCUS_FILE} не найден, пропускаю")
        return True
    
    with open(QUARTERLY_FOCUS_FILE, 'r', encoding='utf-8') as f:
        focus_content = f.read()
    
    # Обновляем каждую колонку
    for quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
        section_pattern = rf'## 🎯 {quarter} {GOALS_YEAR}.*?(?=## |```|%%|$)'
        section_match = re.search(section_pattern, focus_content, re.DOTALL)
        
        if section_match:
            # Создаем новый контент секции
            new_section = f"## 🎯 {quarter} {GOALS_YEAR} ("
            if quarter == 'Q1':
                new_section += "Январь - Март"
            elif quarter == 'Q2':
                new_section += "Апрель - Июнь"
            elif quarter == 'Q3':
                new_section += "Июль - Сентябрь"
            else:
                new_section += "Октябрь - Декабрь"
            new_section += ")\n\n"
            
            # Добавляем цели
            active_goals = [g for g, c in goals_by_quarter[quarter] if not c]
            for goal_text in active_goals:
                new_section += f"- [ ] {goal_text}\n"
            
            # Если нет целей, добавляем пустую задачу
            if not active_goals:
                new_section += "- [ ] \n"
            
            new_section += "\n"
            
            # Заменяем секцию
            focus_content = focus_content[:section_match.start()] + new_section + focus_content[section_match.end():]
    
    # Обновляем дедлайны
    deadlines_pattern = r'## 📅 Дедлайны.*?(?=## |```|$)'
    deadlines_match = re.search(deadlines_pattern, focus_content, re.DOTALL)
    
    if deadlines_match:
        new_deadlines = "## 📅 Дедлайны (не зависят от тебя)\n\n"
        for goal_text, is_completed in goals_by_quarter['deadlines']:
            if not is_completed:
                new_deadlines += f"- [ ] {goal_text}\n"
        
        if not any(not c for _, c in goals_by_quarter['deadlines']):
            new_deadlines += f"- [ ] Закончить ШАД (июнь {GOALS_YEAR}) #цель/учеба #дедлайн/Q2\n"
        
        focus_content = focus_content[:deadlines_match.start()] + new_deadlines + focus_content[deadlines_match.end():]
    
    # Сохраняем
    with open(QUARTERLY_FOCUS_FILE, 'w', encoding='utf-8') as f:
        f.write(focus_content)
    
    print("✅ Файл квартальных фокусов обновлен!")
    
    # Статистика
    for quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
        count = len([g for g, c in goals_by_quarter[quarter] if not c])
        print(f"  {quarter}: {count} целей")
    
    return True


def add_ids_to_tasks() -> bool:
    """Добавляет ID к задачам, у которых его еще нет
    
    ВАЖНО: Эта функция НЕ изменяет структуру файла, только добавляет ID к существующим задачам.
    Структура восстанавливается функцией sort_kanban_tasks().
    """
    if not KANBAN_FILE.exists():
        print(f"⚠️ Канбан-доска не найдена: {KANBAN_FILE}", flush=True)
        return False
    
    with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Разбиваем на секции по заголовкам ##
    section_headers = list(re.finditer(r'^## (.+?)$', content, re.MULTILINE))
    
    if not section_headers:
        # Нет секций - файл уже сломан или пустой
        print("⚠️ Не найдено секций в файле, пропускаем добавление ID", flush=True)
        return False
    
    tasks_without_id = []
    import uuid
    
    # Обрабатываем каждую секцию отдельно
    for i, header_match in enumerate(section_headers):
        section_name = header_match.group(1).strip()
        header_start = header_match.end()
        
        # Определяем конец секции
        if i + 1 < len(section_headers):
            section_end = section_headers[i + 1].start()
        else:
            settings_match = re.search(r'%% kanban:settings', content[header_start:])
            if settings_match:
                section_end = header_start + settings_match.start()
            else:
                section_end = len(content)
        
        section_content = content[header_start:section_end]
        
        # Ищем задачи в этой секции
        task_pattern = r'(- \[[ x]\]\s+.+?)(?=\n- \[|\n## |\n%%|$)'
        for match in re.finditer(task_pattern, section_content, re.DOTALL):
            task_text = match.group(1)
            # Проверяем наличие ID
            if not re.search(r'🆔 ID:', task_text):
                # Вычисляем абсолютную позицию в файле
                abs_start = header_start + match.start()
                abs_end = header_start + match.end()
                tasks_without_id.append((abs_start, abs_end, task_text))
    
    if not tasks_without_id:
        print("✅ Все задачи уже имеют ID", flush=True)
        return True
    
    print(f"🔄 Найдено {len(tasks_without_id)} задач без ID, добавляем...", flush=True)
    
    # Добавляем ID к каждой задаче (с конца, чтобы не сбить индексы)
    for start, end, task_text in reversed(tasks_without_id):
        # Генерируем ID
        task_id = str(uuid.uuid4())[:8]
        # Добавляем ID после даты создания, если есть
        id_line = f"\t🆔 ID: {task_id}"
        task_lines = task_text.rstrip().split('\n')
        
        # Ищем строку с датой создания
        date_line_index = None
        for idx, line in enumerate(task_lines):
            if '📅 Создано:' in line:
                date_line_index = idx
                break
        
        if date_line_index is not None:
            # Вставляем после даты
            new_task_lines = task_lines[:date_line_index + 1] + [id_line] + task_lines[date_line_index + 1:]
        else:
            # Нет даты, добавляем в конец
            new_task_lines = task_lines + [id_line]
        
        new_task_text = '\n'.join(new_task_lines)
        
        # Заменяем в содержимом
        content = content[:start] + new_task_text + content[end:]
    
    # Сохраняем
    with open(KANBAN_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Добавлено ID к {len(tasks_without_id)} задачам", flush=True)
    return True


def get_task_id_from_text(task_text: str) -> Optional[str]:
    """Извлекает ID задачи из текста, или генерирует хэш для старых задач"""
    # Ищем явный ID
    id_match = re.search(r'🆔 ID: ([a-f0-9-]+)', task_text)
    if id_match:
        return id_match.group(1)
    
    # Для старых задач без ID генерируем стабильный хэш
    # Используем стабильные характеристики: дата создания + категория + приоритет + первые 50 символов названия
    date_match = re.search(r'📅 Создано: (\d{4}-\d{2}-\d{2})', task_text)
    category_match = re.search(r'#цель/([^\s#]+)', task_text)
    priority_match = re.search(r'#приоритет/(высокий|средний|низкий)', task_text)
    
    # Извлекаем название (убираем теги и метаданные)
    task_name = re.sub(r'\s*#цель/[^\s#]+.*', '', task_text).strip()
    task_name = re.sub(r'\s*#приоритет/[^\s#]+.*', '', task_name).strip()
    task_name = re.sub(r'\s*#дедлайн/[^\s#]+.*', '', task_name).strip()
    task_name = re.sub(r'\s*📅 Создано:.*', '', task_name).strip()
    task_name = re.sub(r'\s*🆔 ID:.*', '', task_name).strip()
    normalized_task_name = task_name.replace('\\$', '$').replace('\\\\', '\\')
    
    # Формируем строку для хэширования
    hash_parts = []
    if date_match:
        hash_parts.append(date_match.group(1))
    if category_match:
        hash_parts.append(category_match.group(1))
    if priority_match:
        hash_parts.append(priority_match.group(1))
    # Берем первые 50 символов названия для стабильности
    hash_parts.append(normalized_task_name[:50])
    
    if hash_parts:
        hash_str = '|'.join(hash_parts)
        # Генерируем короткий хэш (8 символов, как у UUID)
        return hashlib.md5(hash_str.encode('utf-8')).hexdigest()[:8]
    
    return None


def get_kanban_state() -> Dict[str, str]:
    """Извлекает текущее состояние канбан-доски: task_id -> колонка
    
    Использует уникальный ID задачи (или хэш для старых задач) для отслеживания
    переименованных задач.
    """
    if not KANBAN_FILE.exists():
        return {}
    
    with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    state = {}
    
    # Разбиваем на секции по заголовкам ##. Заголовок — только одна строка ([^\n]+), иначе при одном \n после ## в column_name попадал бы весь текст до \n\n и в логах task_moved писался мусор в to/from.
    section_pattern = r'## ([^\n]+)\n\n(.*?)(?=\n## |\n%%|$)'
    
    for match in re.finditer(section_pattern, content, re.DOTALL):
        column_name = match.group(1).strip()
        section_content = match.group(2).strip()
        
        # Парсим задачи из секции
        task_pattern = r'- \[[ x]\]\s+(.+?)(?=\n- \[|$)'
        task_matches = re.finditer(task_pattern, section_content, re.DOTALL)
        
        for task_match in task_matches:
            task_text = task_match.group(1).strip()
            
            # Получаем ID задачи (явный или хэш)
            task_id = get_task_id_from_text(task_text)
            
            if task_id:
                state[task_id] = column_name
    
    return state


def _trim_task_text_to_item(text: str) -> str:
    """Убирает из текста задачи захваченный мусор: следующий заголовок секции (## ) или блок (%%)."""
    for sep in ('\n## ', '\n%%'):
        if sep in text:
            text = text.split(sep)[0]
    return text.strip()


def get_task_title_by_id(task_id: str, kanban_content: str) -> Optional[str]:
    """Получает название задачи по её ID из содержимого канбан-доски"""
    # Ищем задачу с указанным ID. Останавливаемся на следующей задаче, секции (## ) или %%, иначе в title попадает мусор.
    task_pattern = r'- \[[ x]\]\s+(.+?)(?=\n- \[|\n## |\n%%|$)'
    for match in re.finditer(task_pattern, kanban_content, re.DOTALL):
        task_text = _trim_task_text_to_item(match.group(1).strip())
        found_id = get_task_id_from_text(task_text)
        if found_id == task_id:
            # Извлекаем название
            task_name = re.sub(r'\s*#цель/[^\s#]+.*', '', task_text).strip()
            task_name = re.sub(r'\s*#приоритет/[^\s#]+.*', '', task_name).strip()
            task_name = re.sub(r'\s*#дедлайн/[^\s#]+.*', '', task_name).strip()
            task_name = re.sub(r'\s*📅 Создано:.*', '', task_name).strip()
            task_name = re.sub(r'\s*🆔 ID:.*', '', task_name).strip()
            task_name = _trim_task_text_to_item(task_name)
            normalized_task_name = task_name.replace('\\$', '$').replace('\\\\', '\\')
            # Одна строка без лишних пробелов — для логов и отображения
            normalized_task_name = re.sub(r'\s+', ' ', normalized_task_name).strip()
            return normalized_task_name
    return None


def get_task_category_from_text(task_text: str) -> Optional[str]:
    """Извлекает категорию из текста задачи (#цель/...). Для логирования и графиков."""
    m = re.search(r'#цель/([^\s#]+)', task_text)
    return m.group(1) if m else None


def get_task_category_by_id(task_id: str, kanban_content: str) -> Optional[str]:
    """Получает категорию задачи по ID из содержимого канбан-доски."""
    task_pattern = r'- \[[ x]\]\s+(.+?)(?=\n- \[|\n## |\n%%|$)'
    for match in re.finditer(task_pattern, kanban_content, re.DOTALL):
        task_text = _trim_task_text_to_item(match.group(1).strip())
        if get_task_id_from_text(task_text) == task_id:
            return get_task_category_from_text(task_text)
    return None


def log_task_movements(logger: 'ActionLogger', previous_state: Dict[str, str], current_state: Dict[str, str]):
    """Логирует перемещения задач между колонками
    
    Использует ID задач для отслеживания, что позволяет корректно обрабатывать переименования.
    """
    # Загружаем содержимое файла для получения названий задач
    if not KANBAN_FILE.exists():
        return
    
    with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
        kanban_content = f.read()
    
    # Обрабатываем текущее состояние
    for task_id, current_column in current_state.items():
        previous_column = previous_state.get(task_id)
        
        # Если задача не была в предыдущем состоянии - это новая задача (создание логируется ботом)
        if previous_column is None:
            continue
        
        # Если задача переместилась в другую колонку
        if previous_column != current_column:
            # Получаем текущее название и категорию задачи (категория для графиков)
            task_title = get_task_title_by_id(task_id, kanban_content)
            if task_title:
                category = get_task_category_by_id(task_id, kanban_content)
                logger.log_task_moved(
                    task_title, previous_column, current_column, task_id=task_id, category=category
                )
                # Графики «Завершено по категориям» и «Активность за день» считают только task_completed — дублируем при переходе в Сделано
                if current_column == DONE_COLUMN:
                    logger.log_task_completed(task_title, task_id=task_id, category=category)


def run_all() -> bool:
    """Запускает все операции обслуживания vault"""
    print("=" * 50)
    print("🚀 Обслуживание vault")
    print("=" * 50)
    print()
    
    results = []
    
    # 0. Сохраняем состояние ДО сортировки для логирования перемещений
    state_file = LOGS_DIR / "kanban_state.json"
    previous_state = {}
    if state_file.exists():
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                previous_state = json.load(f)
            
            # МИГРАЦИЯ: Преобразуем старые записи в новый формат (ID вместо дата|название)
            # Для этого нужно найти задачи в файле и сопоставить их с ID
            if previous_state and any('|' in key or (not key.startswith('h') and len(key) > 8) for key in previous_state.keys()):
                # Есть старые записи - пытаемся их мигрировать
                current_state_temp = get_kanban_state()
                migrated_state = {}
                
                # Загружаем содержимое файла для миграции
                with open(KANBAN_FILE, 'r', encoding='utf-8') as f:
                    kanban_content = f.read()
                
                for old_key, old_column in previous_state.items():
                    # Если ключ уже в формате ID (8 символов hex) - оставляем как есть
                    if len(old_key) == 8 and all(c in '0123456789abcdef' for c in old_key):
                        migrated_state[old_key] = old_column
                    elif '|' in old_key:
                        # Старый формат дата|название - ищем задачу и используем её ID
                        date, old_name = old_key.split('|', 1)
                        found = False
                        for task_id, _ in current_state_temp.items():
                            task_title = get_task_title_by_id(task_id, kanban_content)
                            if task_title == old_name:
                                migrated_state[task_id] = old_column
                                found = True
                                break
                        
                        if not found:
                            # Не нашли - генерируем хэш для обратной совместимости
                            hash_str = f"{date}|{old_name}"
                            task_id = hashlib.md5(hash_str.encode('utf-8')).hexdigest()[:8]
                            migrated_state[task_id] = old_column
                    else:
                        # Старый формат только название - пытаемся найти по названию
                        found = False
                        for task_id, _ in current_state_temp.items():
                            task_title = get_task_title_by_id(task_id, kanban_content)
                            if task_title == old_key:
                                migrated_state[task_id] = old_column
                                found = True
                                break
                        
                        if not found:
                            # Не нашли - генерируем хэш для обратной совместимости
                            task_id = hashlib.md5(old_key.encode('utf-8')).hexdigest()[:8]
                            migrated_state[task_id] = old_column
                
                previous_state = migrated_state
        except Exception as e:
            print(f"⚠️ Ошибка при загрузке состояния: {e}")
            previous_state = {}
    
    current_state_before = get_kanban_state()
    
    # 0.5. Добавляем ID к задачам без ID (миграция)
    results.append(("Добавление ID к задачам", add_ids_to_tasks()))
    print()
    
    # 1. Синхронизация квартальных фокусов
    results.append(("Синхронизация квартальных фокусов", sync_quarterly_focus()))
    print()
    
    # 2. Сортировка задач
    results.append(("Сортировка задач", sort_kanban_tasks()))
    print()
    
    # 2.5. Логируем перемещения задач (между текущим состоянием до сортировки и предыдущим)
    try:
        from planning_bot.services.action_logger import ActionLogger
        logger = ActionLogger(logs_dir=ACTION_LOGS_DIR)
        log_task_movements(logger, previous_state, current_state_before)
    except Exception as e:
        print(f"⚠️ Ошибка при логировании перемещений: {e}")
    
    # 2.6. Сохраняем текущее состояние ПОСЛЕ сортировки для следующего запуска
    try:
        current_state_after = get_kanban_state()  # Получаем состояние после сортировки
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(current_state_after, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка при сохранении состояния: {e}")
    
    # 3. Завершённые задачи логируются только при переходе в «Сделано» (log_task_movements и kanban_monitor).
    # Массовая выгрузка всех задач из колонки «Сделано» в лог отключена — она давала нереалистичные цифры на графиках.
    pass

    # 4. Синхронизация Календарь.txt → Календарь.json
    try:
        from planning_bot.tools.calendar_sync import run_calendar_sync
        results.append(("Синхронизация календаря", run_calendar_sync()))
    except Exception as e:
        print(f"⚠️ Ошибка при синхронизации календаря: {e}")
        results.append(("Синхронизация календаря", False))

    # 5. Синхронизация контекста Mac (шорткат «Контекст (Obsidian)»)
    try:
        from planning_bot.tools.context_sync import run_context_sync
        results.append(("Синхронизация контекста", run_context_sync()))
    except Exception as e:
        print(f"⚠️ Ошибка при синхронизации контекста: {e}")
        results.append(("Синхронизация контекста", False))
    print()

    # 6. Инжест iPhone-контекста из Gmail IMAP (iphone_mail_sync)
    # Запускается только если заданы GMAIL_IMAP_USER / GMAIL_IMAP_APP_PASSWORD
    if os.environ.get("GMAIL_IMAP_USER") and os.environ.get("GMAIL_IMAP_APP_PASSWORD"):
        try:
            from planning_bot.tools.iphone_mail_sync import run_iphone_mail_sync

            # По умолчанию только письма «за сегодня» в IPHONE_SYNC_TZ; IPHONE_MAIL_SYNC_TODAY_ONLY=0 — бэкфилл
            _to = os.environ.get("IPHONE_MAIL_SYNC_TODAY_ONLY", "1").lower() not in (
                "0",
                "false",
                "no",
                "off",
            )
            res = run_iphone_mail_sync(today_only=_to)
            ok = res.get("ok", False)
            written = res.get("written", 0)
            print(
                f"   iphone_mail_sync: ok={ok} written={written} today_only={res.get('today_only')}"
                + (f" errors={res.get('errors')}" if res.get("errors") else ""),
                flush=True,
            )
            results.append(("iPhone mail sync", ok or written == 0))
        except Exception as e:
            print(f"⚠️ Ошибка при iPhone mail sync: {e}")
            results.append(("iPhone mail sync", False))
    else:
        print("   iphone_mail_sync: пропуск (GMAIL_IMAP_USER не задан)", flush=True)
    print()

    # 7. JSON по iPhone-снапшотам (iphone_today.json / iphone_week.json)
    try:
        from planning_bot.tools.iphone_context_sync import run_iphone_context_sync

        results.append(("Синхронизация iPhone JSON", run_iphone_context_sync()))
    except Exception as e:
        print(f"⚠️ Ошибка при iphone_context_sync: {e}")
        results.append(("Синхронизация iPhone JSON", False))
    print()

    # Итоги
    print("=" * 50)
    print("📊 Итоги:")
    print("=" * 50)
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print()
    print(f"Успешно: {success_count}/{total_count}")
    
    return success_count == total_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-only", action="store_true", help="Только добавить ID к задачам без ID")
    args = parser.parse_args()
    if args.ids_only:
        success = add_ids_to_tasks()
    else:
        success = run_all()
    sys.exit(0 if success else 1)
