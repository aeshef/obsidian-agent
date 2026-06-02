#!/usr/bin/env python3
"""
Синхронизация vault для knowledge_bot
Сервер -> Локальный (бот работает на сервере, синхронизирует данные на локальную машину)
Этот скрипт запускается на ЛОКАЛЬНОЙ машине для подтягивания данных с сервера
"""
import os
import subprocess
import sys
from pathlib import Path

# Путь к vault из переменных окружения
VAULT_PATH = Path(os.getenv("VAULT_PATH", str(Path.home() / "Obsidian Vault")))

def _sync_paths() -> list[str]:
    from shared.vault_layout import knowledge_subdir

    return [knowledge_subdir()]

def sync_from_server(server_host: str, server_vault_path: str, local_vault_path: Path):
    """Синхронизация с сервера на локальную машину (сервер -> локальный)"""
    print(f"🔄 Синхронизация с сервера {server_host}...")
    
    for sync_path in _sync_paths():
        server_path = f"{server_host}:{server_vault_path}/{sync_path}/"
        local_path = local_vault_path / sync_path
        
        # Создаем директорию если её нет
        local_path.mkdir(parents=True, exist_ok=True)
        
        print(f"  📁 {sync_path}...")
        
        # rsync с исключением временных файлов
        # БЕЗ --delete: безопасная синхронизация (только добавляет/обновляет, не удаляет)
        cmd = [
            "rsync",
            "-avz",  # archive, verbose, compress
            "--exclude", "*.tmp",
            "--exclude", "*.swp",
            "--exclude", ".DS_Store",
            "--exclude", "__pycache__",
            server_path,
            str(local_path) + "/"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"    ✅ Синхронизировано")
        except subprocess.CalledProcessError as e:
            print(f"    ❌ Ошибка: {e.stderr}")
            return False
    
    print("✅ Синхронизация завершена")
    return True

def sync_to_server(server_host: str, server_vault_path: str, local_vault_path: Path):
    """Синхронизация с локальной машины на сервер (локальный -> сервер, для бэкапа)"""
    print(f"🔄 Синхронизация на сервер {server_host}...")
    
    for sync_path in _sync_paths():
        local_path = local_vault_path / sync_path
        server_path = f"{server_host}:{server_vault_path}/{sync_path}/"
        
        if not local_path.exists():
            print(f"  ⚠️ Путь {local_path} не существует, пропускаю")
            continue
        
        print(f"  📁 {sync_path}...")
        
        # rsync с исключением временных файлов
        # БЕЗ --delete: безопасная синхронизация (только добавляет/обновляет, не удаляет)
        cmd = [
            "rsync",
            "-avz",  # archive, verbose, compress
            "--exclude", "*.tmp",
            "--exclude", "*.swp",
            "--exclude", ".DS_Store",
            "--exclude", "__pycache__",
            str(local_path) + "/",
            server_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"    ✅ Синхронизировано")
        except subprocess.CalledProcessError as e:
            print(f"    ❌ Ошибка: {e.stderr}")
            return False
    
    print("✅ Синхронизация завершена")
    return True

if __name__ == "__main__":
    # Параметры из переменных окружения
    SERVER_HOST = os.getenv("SYNC_SERVER_HOST")
    [REDACTED]
    SYNC_DIRECTION = os.getenv("SYNC_DIRECTION", "from")  # from (сервер->локальный) по умолчанию
    
    if not SERVER_HOST:
        print("❌ Установи SYNC_SERVER_HOST в переменных окружения")
        sys.exit(1)
    
    if SYNC_DIRECTION == "from":
        success = sync_from_server(SERVER_HOST, SERVER_VAULT_PATH, VAULT_PATH)
    else:
        success = sync_to_server(SERVER_HOST, SERVER_VAULT_PATH, VAULT_PATH)
    
    sys.exit(0 if success else 1)
