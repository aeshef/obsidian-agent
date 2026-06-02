#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
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
    print(pdmsg("auto_406ba62c6f"))

from planning_bot.core.config import KANBAN_FILE
from planning_bot.tools.vault_maintenance import add_ids_to_tasks

# (comment)
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
    'Type helper.'
    
    def __init__(self, kanban_path: Path, debounce_seconds: float = 2.0):
        'Operation implementation.'
        self.kanban_path = kanban_path
        self.debounce_seconds = debounce_seconds
        self.last_modified = 0.0
        self.pending_call = None
    
    def on_modified(self, event):
        'Operation implementation.'
        if isinstance(event, FileModifiedEvent):
            # (comment)
            if Path(event.src_path).resolve() == self.kanban_path.resolve():
                current_time = time.time()
                # (comment)
                if current_time - self.last_modified < self.debounce_seconds:
                    return
                
                self.last_modified = current_time
                logger.info(pdmsg("auto_2710b69820", _p1=event.src_path))
                
                # (comment)
                time.sleep(0.5)
                
                try:
                    logger.info(pdmsg("auto_6bcee8c814"))
                    result = add_ids_to_tasks()
                    if result:
                        logger.info(pdmsg("auto_39f88b49b8"))
                    else:
                        logger.warning(pdmsg("auto_ebf057fb07"))
                except Exception as e:
                    logger.error(pdmsg("auto_cb8aff6c9e", _p1=e), exc_info=True)


def run_add_ids_periodically(interval_seconds: int = 300):
    'Operation implementation.'
    while True:
        time.sleep(interval_seconds)
        try:
            logger.info(pdmsg("auto_0882f1bcd1"))
            add_ids_to_tasks()
        except Exception as e:
            logger.error(pdmsg("auto_a2aa7d905f", _p1=e), exc_info=True)


def main():
    'Operation implementation.'
    if not WATCHDOG_AVAILABLE:
        logger.error(pdmsg("auto_2bf5f2190c"))
        sys.exit(1)
    
    kanban_path = Path(KANBAN_FILE).resolve()
    
    if not kanban_path.exists():
        logger.error(pdmsg("auto_9310c794b6", _p1=kanban_path))
        sys.exit(1)
    
    logger.info(pdmsg("auto_528da68a5f", _p1=kanban_path))
    logger.info(pdmsg("auto_94f191654e", _p1=kanban_path.parent))
    
    # (comment)
    event_handler = KanbanFileHandler(kanban_path, debounce_seconds=2.0)
    
    # (comment)
    observer = Observer()
    observer.schedule(event_handler, str(kanban_path.parent), recursive=False)
    
    observer.start()
    logger.info(pdmsg("auto_87d95d80a6"))
    
    # (comment)
    periodic_thread = threading.Thread(target=run_add_ids_periodically, kwargs={"interval_seconds": 300}, daemon=True)
    periodic_thread.start()
    logger.info(pdmsg("auto_cbc7c75467"))
    
    try:
        # (comment)
        logger.info(pdmsg("auto_26f181c8b7"))
        add_ids_to_tasks()
        
        # (comment)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info(pdmsg("auto_0502850db6"))
        observer.stop()
    
    observer.join()
    logger.info(pdmsg("auto_a83ae93d8e"))


if __name__ == "__main__":
    main()
