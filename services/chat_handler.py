"""Обработчик чат-режима: контекст, история переписки, LLM-ответ."""
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Optional

from planning_bot.core.config import ACTION_LOGS_DIR, LOG_DIR, BOT_DIR
from planning_bot.core.settings import load_prompt, get_config_path

if TYPE_CHECKING:
    from planning_bot.core.llm import DeepSeekClient
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.goals import GoalsManager

logger = logging.getLogger(__name__)

# Файл хранения истории чата
CHAT_HISTORY_FILE = LOG_DIR / "chat_history.json"
# Максимум сообщений в истории (rolling window)
HISTORY_WINDOW = 20
# Максимум задач бэклога в компактном контексте
BACKLOG_LIMIT = 30


class ChatHandler:
    """Сборка контекста и ответ LLM в режиме чата."""

    def __init__(
        self,
        llm: "DeepSeekClient",
        kanban: "KanbanBoard",
        goals_manager: "GoalsManager",
    ):
        self.llm = llm
        self.kanban = kanban
        self.goals_manager = goals_manager
        self.config_path = get_config_path()

    # ------------------------------------------------------------------ #
    # История                                                              #
    # ------------------------------------------------------------------ #

    def load_history(self, chat_id: int) -> List[Dict[str, str]]:
        """Загружает историю переписки для данного chat_id."""
        try:
            if CHAT_HISTORY_FILE.exists():
                with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get(str(chat_id), [])
        except Exception as e:
            logger.warning("Не удалось загрузить историю чата: %s", e)
        return []

    def save_history(self, chat_id: int, messages: List[Dict[str, str]]) -> None:
        """Сохраняет историю (rolling window HISTORY_WINDOW сообщений)."""
        try:
            CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            data: Dict = {}
            if CHAT_HISTORY_FILE.exists():
                with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            # Храним только последние HISTORY_WINDOW сообщений
            data[str(chat_id)] = messages[-HISTORY_WINDOW:]
            with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Не удалось сохранить историю чата: %s", e)

    def append_to_history(
        self, chat_id: int, role: str, content: str
    ) -> List[Dict[str, str]]:
        """Добавляет одно сообщение в историю и возвращает обновлённый список."""
        history = self.load_history(chat_id)
        history.append({"role": role, "content": content})
        self.save_history(chat_id, history)
        return history

    # ------------------------------------------------------------------ #
    # Сборка контекста                                                     #
    # ------------------------------------------------------------------ #

    def assemble_context(self, user_message: str = "") -> str:
        """Собирает компактный контекст: цели + kanban + опциональные логи."""
        parts: List[str] = []

        # 1. Годовые цели
        try:
            goals = self.goals_manager.get_goals()
            if goals:
                parts.append("### Годовые цели:\n" + "\n".join(f"- {g}" for g in goals[:10]))
        except Exception as e:
            logger.debug("Не удалось загрузить цели: %s", e)

        # 2. Квартальные фокусы
        try:
            qf = self.goals_manager.get_quarterly_focus()
            if qf:
                parts.append("### Квартальные фокусы:\n" + "\n".join(f"- {g}" for g in qf[:10]))
        except Exception as e:
            logger.debug("Не удалось загрузить квартальные фокусы: %s", e)

        # 3. Контекст целей (goals_context.md)
        try:
            gc = self.goals_manager.get_goals_context()
            if gc:
                parts.append(f"### Контекст целей:\n{gc[:600]}")
        except Exception as e:
            logger.debug("Не удалось загрузить goals_context: %s", e)

        # 4. Компактный срез канбана
        try:
            all_tasks = self.kanban.get_tasks(exclude_today=False, exclude_blocked=False)
            in_progress = [t for t in all_tasks if t.get("column") == "🔄 В работе"]
            blocked = [t for t in all_tasks if t.get("column") == "🚫 Заблокировано"]
            backlog = [t for t in all_tasks if t.get("column") == "📋 Бэклог"]

            def fmt(t: Dict) -> str:
                pri = t.get("priority") or "—"
                cat = t.get("category") or "—"
                dl = f" | дедлайн {t['deadline']}" if t.get("deadline") else ""
                return f"  [{pri}] {t['title']} | {cat}{dl}"

            kanban_lines = ["### Доска задач (снимок):"]
            if in_progress:
                kanban_lines.append("🔄 В работе:")
                kanban_lines.extend(fmt(t) for t in in_progress)
            if blocked:
                kanban_lines.append("🚫 Заблокировано:")
                kanban_lines.extend(fmt(t) for t in blocked[:10])
            if backlog:
                kanban_lines.append(f"📋 Бэклог (первые {min(len(backlog), BACKLOG_LIMIT)}):")
                kanban_lines.extend(fmt(t) for t in backlog[:BACKLOG_LIMIT])
            parts.append("\n".join(kanban_lines))
        except Exception as e:
            logger.debug("Не удалось загрузить канбан: %s", e)

        # 5. Логи действий — только при ключевых словах в запросе
        keywords_need_logs = (
            "история", "паттерн", "месяц", "неделя", "прогресс",
            "динамик", "последн", "тренд", "сколько", "когда",
        )
        msg_lower = user_message.lower()
        if any(kw in msg_lower for kw in keywords_need_logs):
            try:
                logs_text = self._get_recent_action_logs(days=60)
                if logs_text:
                    parts.append(f"### Логи действий (последние 60 дней):\n{logs_text}")
            except Exception as e:
                logger.debug("Не удалось загрузить логи: %s", e)

        return "\n\n".join(parts)

    def _get_recent_action_logs(self, days: int = 60) -> str:
        """Читает файлы логов действий за последние `days` дней."""
        from datetime import datetime, timedelta
        from planning_bot.core.config import ACTION_LOG_PREFIX

        if not ACTION_LOGS_DIR.exists():
            return ""

        cutoff = datetime.now() - timedelta(days=days)
        lines: List[str] = []
        for log_file in sorted(ACTION_LOGS_DIR.glob(f"{ACTION_LOG_PREFIX}*.md")):
            try:
                # Имя файла: "📊 Логи_Действий_2026-04.md"
                date_part = log_file.stem.replace(ACTION_LOG_PREFIX, "")
                file_month = datetime.strptime(date_part, "%Y-%m")
                if file_month < cutoff.replace(day=1):
                    continue
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        # Берём только строки с данными (дата + действие)
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and "|" in stripped:
                            lines.append(stripped)
            except Exception:
                continue

        # Ограничиваем размер (~3000 токенов ≈ 12000 символов)
        result = "\n".join(lines[-400:])
        return result[:12000]

    # ------------------------------------------------------------------ #
    # Генерация ответа                                                     #
    # ------------------------------------------------------------------ #

    def respond(
        self,
        user_message: str,
        chat_id: int,
        extra_context: str = "",
    ) -> str:
        """Формирует ответ LLM с контекстом и историей переписки."""
        try:
            system_prompt = load_prompt(self.config_path, "conversation")
        except Exception as e:
            logger.warning("Не удалось загрузить conversation prompt: %s", e)
            system_prompt = "Ты — персональный ассистент по планированию. Отвечай по-русски, кратко и по делу."

        context_str = self.assemble_context(user_message)
        if extra_context:
            context_str = extra_context + "\n\n" + context_str

        # Системный промпт + контекст
        system_with_context = system_prompt
        if context_str:
            system_with_context += f"\n\n---\n### ТВОЙ КОНТЕКСТ (обновляется при каждом запросе):\n{context_str}"

        # История + новое сообщение
        history = self.load_history(chat_id)
        messages = [{"role": "system", "content": system_with_context}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        reply = self.llm.chat(messages, temperature=0.8)

        # Сохраняем диалог в историю
        new_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ]
        self.save_history(chat_id, new_history)

        return reply
