#!/usr/bin/env python3
"""
Watcher для автоматического добавления ID к задачам при изменении канбан-доски.

Запускается в фоне и отслеживает изменения файла канбана.
При сохранении файла автоматически добавляет ID к задачам без ID.

Использование:
    python scripts/watch_and_add_ids.py
    
Или через launchd (macOS):
    Шаблон scripts/com.example.planning_bot.add_ids.plist.example; установка: scripts/setup_watcher.sh
"""

import sys
import time
import logging
import threading
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("⚠️ watchdog не установлен. Установите: pip install watchdog")

from planning_bot.core.config import KANBAN_FILE
from planning_bot.tools.vault_maintenance import add_ids_to_tasks

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'add_ids_watcher.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class KanbanFileHandler(FileSystemEventHandler):
    """Обработчик изменений файла канбана"""
    
    def __init__(self, kanban_path: Path, debounce_seconds: float = 2.0):
        """
        Args:
            kanban_path: путь к файлу канбана
            debounce_seconds: задержка перед обработкой (чтобы избежать множественных срабатываний)
        """
        self.kanban_path = kanban_path
        self.debounce_seconds = debounce_seconds
        self.last_modified = 0.0
        self.pending_call = None
    
    def on_modified(self, event):
        """Вызывается при изменении файла"""
        if isinstance(event, FileModifiedEvent):
            # Проверяем, что это наш файл канбана
            if Path(event.src_path).resolve() == self.kanban_path.resolve():
                current_time = time.time()
                # Debounce: игнорируем изменения, если прошло меньше debounce_seconds
                if current_time - self.last_modified < self.debounce_seconds:
                    return
                
                self.last_modified = current_time
                logger.info(f"📝 Обнаружено изменение файла канбана: {event.src_path}")
                
                # Небольшая задержка перед обработкой (файл может еще записываться)
                time.sleep(0.5)
                
                try:
                    logger.info("🔄 Запуск добавления ID к задачам без ID...")
                    result = add_ids_to_tasks()
                    if result:
                        logger.info("✅ ID добавлены к задачам (если были задачи без ID)")
                    else:
                        logger.warning("⚠️ Не удалось добавить ID (файл не найден или ошибка)")
                except Exception as e:
                    logger.error(f"❌ Ошибка при добавлении ID: {e}", exc_info=True)


def run_add_ids_periodically(interval_seconds: int = 300):
    """Периодически запускает add_ids_to_tasks (подстраховка, если события сохранения не сработали)."""
    while True:
        time.sleep(interval_seconds)
        try:
            logger.info("🔄 Периодическая проверка: добавление ID к задачам без ID...")
            add_ids_to_tasks()
        except Exception as e:
            logger.error(f"❌ Ошибка при периодическом добавлении ID: {e}", exc_info=True)


def main():
    """Главная функция watcher'а"""
    if not WATCHDOG_AVAILABLE:
        logger.error("❌ watchdog не установлен. Установите: pip install watchdog")
        sys.exit(1)
    
    kanban_path = Path(KANBAN_FILE).resolve()
    
    if not kanban_path.exists():
        logger.error(f"❌ Файл канбана не найден: {kanban_path}")
        sys.exit(1)
    
    logger.info(f"👀 Запуск watcher для файла: {kanban_path}")
    logger.info(f"📁 Родительская директория: {kanban_path.parent}")
    
    # Создаем обработчик событий
    event_handler = KanbanFileHandler(kanban_path, debounce_seconds=2.0)
    
    # Создаем observer и начинаем наблюдение
    observer = Observer()
    observer.schedule(event_handler, str(kanban_path.parent), recursive=False)
    
    observer.start()
    logger.info("✅ Watcher запущен. Нажмите Ctrl+C для остановки.")
    
    # Подстраховка: раз в 5 минут проверяем и добавляем ID (на случай если событие сохранения не сработало)
    periodic_thread = threading.Thread(target=run_add_ids_periodically, kwargs={"interval_seconds": 300}, daemon=True)
    periodic_thread.start()
    logger.info("✅ Периодическая проверка каждые 5 мин включена.")
    
    try:
        # Добавляем ID сразу при запуске (на случай, если есть задачи без ID)
        logger.info("🔄 Первоначальная проверка и добавление ID...")
        add_ids_to_tasks()
        
        # Ждем бесконечно
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Остановка watcher...")
        observer.stop()
    
    observer.join()
    logger.info("✅ Watcher остановлен")


if __name__ == "__main__":
    main()
