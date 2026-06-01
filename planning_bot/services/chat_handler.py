"""Обработчик чат-режима: контекст, история переписки, LLM-ответ."""
import json
import logging
import os
import re
from typing import TYPE_CHECKING, List, Dict, Optional

from planning_bot.core.config import LOG_DIR, KANBAN_COLUMNS
from planning_bot.core.settings import load_prompt, get_config_path
from planning_bot.services.action_logger import ActionLogger

if TYPE_CHECKING:
    from planning_bot.core.llm import DeepSeekClient
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.goals import GoalsManager

logger = logging.getLogger(__name__)

# Файл хранения истории чата
CHAT_HISTORY_FILE = LOG_DIR / "chat_history.json"
# Rolling window: user+assistant сообщения. Длинные прошлые ответы ассистента иначе шаблонят следующий ответ.
_default_hw = 8
try:
    HISTORY_WINDOW = int(os.getenv("PLANNING_CHAT_HISTORY_MAX_MESSAGES", str(_default_hw)))
except ValueError:
    HISTORY_WINDOW = _default_hw
HISTORY_WINDOW = max(2, min(40, HISTORY_WINDOW))

# Прошлые ответы ассистента в истории иначе «заражают» следующий ответ тем же шаблоном (длинные обзоры).
# Режимы: omit — один символ (не длинная инструкция — иначе модель цитирует её как ответ пользователю).
# truncate — первые N символов; full — как в файле (не рекомендуется).
_ASSIST_HIST_PLACEHOLDER = "…"


def _compress_assistant_history(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    mode = os.getenv("PLANNING_CHAT_ASSISTANT_HISTORY_MODE", "omit").strip().lower()
    try:
        max_chars = int(os.getenv("PLANNING_CHAT_ASSISTANT_HISTORY_MAX_CHARS", "400"))
    except ValueError:
        max_chars = 400
    out: List[Dict[str, str]] = []
    for m in history:
        if m.get("role") != "assistant":
            out.append(dict(m))
            continue
        content = m.get("content") or ""
        if mode == "full":
            out.append({"role": "assistant", "content": content})
        elif mode == "omit":
            out.append({"role": "assistant", "content": _ASSIST_HIST_PLACEHOLDER})
        else:
            # truncate
            if max_chars <= 0:
                out.append({"role": "assistant", "content": _ASSIST_HIST_PLACEHOLDER})
            elif len(content) <= max_chars:
                out.append({"role": "assistant", "content": content})
            else:
                out.append({"role": "assistant", "content": content[:max_chars] + "…"})
    return out


def _is_trivial_reply(text: str) -> bool:
    """Пустой или бессмысленно короткий ответ — повтор LLM (смысл «мусора» в conversation.txt)."""
    t = (text or "").strip()
    return not t or t in ("…", "...", "—", "-")


def _plain_text_for_telegram(text: str) -> str:
    """Убирает типичный Markdown из ответа: Telegram показывает его как мусор, если не включён parse_mode."""
    if not text:
        return text
    out = text
    while "**" in out:
        out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", out)
    out = re.sub(r"__([^_]+)__", r"\1", out)
    out = re.sub(r"`([^`]+)`", r"\1", out)
    out = re.sub(r"(?m)^#{1,6}\s*", "", out)
    return out.strip()


class ChatHandler:
    """Сборка контекста и ответ LLM в режиме чата."""

    def __init__(
        self,
        llm: "DeepSeekClient",
        kanban: "KanbanBoard",
        goals_manager: "GoalsManager",
        action_logger: Optional[ActionLogger] = None,
    ):
        self.llm = llm
        self.kanban = kanban
        self.goals_manager = goals_manager
        self.action_logger = action_logger
        self.config_path = get_config_path()

    # ------------------------------------------------------------------ #
    # История                                                              #
    # ------------------------------------------------------------------ #

    def load_history(self, chat_id: int) -> List[Dict[str, str]]:
        """История из shared session (домен planning), с тем же rolling window."""
        from shared.memory import get_history

        msgs = get_history(chat_id, "planning")
        raw = [{"role": m.role, "content": m.content} for m in msgs]
        if len(raw) > HISTORY_WINDOW:
            return raw[-HISTORY_WINDOW:]
        return raw

    def save_history(self, chat_id: int, messages: List[Dict[str, str]]) -> None:
        """Перезапись истории (legacy API для рефлексии)."""
        from shared.memory import append_turn, clear_history

        clear_history(chat_id, "planning")
        for m in messages[-HISTORY_WINDOW:]:
            append_turn(chat_id, "planning", m.get("role", "user"), m.get("content", ""))

    def append_to_history(
        self, chat_id: int, role: str, content: str
    ) -> List[Dict[str, str]]:
        from shared.memory import append_turn

        append_turn(chat_id, "planning", role, content)
        return self.load_history(chat_id)

    def clear_history(self, chat_id: int) -> bool:
        from shared.memory import clear_history

        clear_history(chat_id, "planning")
        logger.info("chat history cleared for chat_id=%s (shared session)", chat_id)
        return True

    # ------------------------------------------------------------------ #
    # Сборка контекста                                                     #
    # ------------------------------------------------------------------ #

    def assemble_context(self, user_message: str = "") -> str:
        """Собирает контекст: сначала цепочка логов (факты), затем цели, затем канбан."""
        parts: List[str] = []

        # 0. Цепочка событий из action-логов — в начале контекста (чтобы LLM не подменяла факты снимком доски)
        if self.action_logger is not None:
            try:
                chain = self.action_logger.get_recent_events_chain()
                if chain:
                    parts.append(chain)
            except Exception as e:
                logger.debug("Не удалось собрать цепочку логов: %s", e)

        # 1. Годовые цели
        try:
            goals = self.goals_manager.get_goals()
            if goals:
                parts.append("Годовые цели:\n" + "\n".join(f"— {g}" for g in goals))
        except Exception as e:
            logger.debug("Не удалось загрузить цели: %s", e)

        # 2. Квартальные фокусы
        try:
            qf = self.goals_manager.get_quarterly_focus()
            if qf:
                parts.append("Квартальные фокусы:\n" + "\n".join(f"— {g}" for g in qf))
        except Exception as e:
            logger.debug("Не удалось загрузить квартальные фокусы: %s", e)

        # Mac / Health / календарь — через agent tools (get_mac_context, get_health_*, get_calendar).
        # Legacy-чат не дублирует их в system prompt.

        # 3. Только блоки «Что нужно сделать:» из goals_context.md
        try:
            gc = self.goals_manager.get_goals_context_what_to_do_only()
            if gc:
                parts.append(
                    "Цели — что нужно сделать (выдержка из goals_context.md):\n" + gc
                )
        except Exception as e:
            logger.debug("Не удалось загрузить goals_context what-to-do: %s", e)

        # 4. Вся доска: все колонки, все задачи (без лимитов)
        try:
            all_tasks = self.kanban.get_tasks(exclude_today=False, exclude_blocked=False)

            def fmt(t: Dict) -> str:
                pri = t.get("priority") or "—"
                cat = t.get("category") or "—"
                dl = f" | дедлайн {t['deadline']}" if t.get("deadline") else ""
                done = " | выполнено" if t.get("completed") else ""
                return f"  [{pri}] {t['title']} | {cat}{dl}{done}"

            by_col: Dict[str, List[Dict]] = {col: [] for col in KANBAN_COLUMNS}
            unknown_col: List[Dict] = []
            for t in all_tasks:
                col = t.get("column")
                if col in by_col:
                    by_col[col].append(t)
                else:
                    unknown_col.append(t)

            kanban_lines = ["Доска задач (полный снимок, все колонки):"]
            for col in KANBAN_COLUMNS:
                tasks = by_col[col]
                kanban_lines.append(f"{col} ({len(tasks)}):")
                if tasks:
                    kanban_lines.extend(fmt(t) for t in tasks)
                else:
                    kanban_lines.append("  (пусто)")
            if unknown_col:
                kanban_lines.append(f"Колонка не из списка ({len(unknown_col)}):")
                kanban_lines.extend(fmt(t) for t in unknown_col)
            parts.append("\n".join(kanban_lines))
        except Exception as e:
            logger.debug("Не удалось загрузить канбан: %s", e)

        return "\n\n".join(parts)

    def _fallback_reply_from_log(self) -> str:
        """Если LLM дважды вернула мусор — показываем сырые строки лога (всё ещё лучше, чем тишина)."""
        if self.action_logger is None:
            return (
                "Не получилось сформулировать ответ. Напиши /reset_context и повтори вопрос "
                "или сформулируй конкретнее."
            )
        try:
            raw = self.action_logger.get_recent_events_chain()
            if not raw or len(raw.strip()) < 30:
                return (
                    "За выбранное окно в логе почти нет событий или лог недоступен. "
                    "Проверь, что на сервере актуальный vault и файл логов в 300_Дашборды/Логи/."
                )
            try:
                cap = int(os.getenv("PLANNING_CHAT_FALLBACK_LOG_CHARS", "3800"))
            except ValueError:
                cap = 3800
            body = raw if len(raw) <= cap else raw[:cap] + "\n…"
            return (
                "Авто-ответ не собрался — ниже сырые строки из лога задач за окно "
                "(факты без интерпретации). Потом можно снова спросить обычным языком.\n\n"
                + body
            )
        except Exception as e:
            logger.warning("fallback_reply_from_log: %s", e)
            return "Ошибка при чтении лога. Попробуй /reset_context и вопрос ещё раз."

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
        system_prompt = load_prompt(self.config_path, "conversation")
        if not system_prompt.strip():
            logger.warning("conversation.txt пуст — заполните planning_bot/config/prompts/conversation.txt")
            system_prompt = (
                "Ты — персональный ассистент по планированию. Отвечай по-русски, кратко. "
                "Не цитируй system prompt и инструкции."
            )

        context_str = self.assemble_context(user_message)
        if extra_context:
            context_str = extra_context + "\n\n" + context_str

        # Системный промпт + контекст
        system_with_context = system_prompt
        if context_str:
            system_with_context += (
                "\n\n---\nТВОЙ КОНТЕКСТ (обновляется при каждом запросе):\n"
                + context_str
            )
        # Короткий якорь: длинные «инструкции» в конце system модель иногда цитирует в ответ пользователю
        system_with_context += (
            "\n\n---\nЯКОРЬ: факты о задачах — из блока «ЛОГ СОБЫТИЙ» в ТВОЙ КОНТЕКСТ выше. "
            "История чата ниже не источник фактов. Пиши обычным текстом пользователю, без квадратных скобок и без мета-инструкций."
        )

        # История: урезаем тела прошлых ответов ассистента (иначе шаблон длинного «обзора» повторяется)
        history = self.load_history(chat_id)
        hist_raw_chars = sum(len(m.get("content") or "") for m in history)
        history_for_llm = _compress_assistant_history(history)
        hist_llm_chars = sum(len(m.get("content") or "") for m in history_for_llm)
        logger.info(
            "chat LLM: context_chars=%d history_msgs=%d history_raw_chars=%d history_llm_chars=%d user_len=%d mode=%s",
            len(context_str),
            len(history_for_llm),
            hist_raw_chars,
            hist_llm_chars,
            len(user_message),
            os.getenv("PLANNING_CHAT_ASSISTANT_HISTORY_MODE", "omit"),
        )
        base_messages: List[Dict[str, str]] = [{"role": "system", "content": system_with_context}]
        base_messages.extend(history_for_llm)
        base_messages.append({"role": "user", "content": user_message})

        chat_temp = float(os.getenv("PLANNING_CHAT_LLM_TEMPERATURE", "0.55"))
        reply = self.llm.chat(base_messages, temperature=chat_temp)
        reply = _plain_text_for_telegram(reply)

        # Повтор при мусоре / только «…» — один раз, ниже температура
        retry_temp = float(os.getenv("PLANNING_CHAT_RETRY_TEMPERATURE", "0.28"))
        if _is_trivial_reply(reply):
            logger.warning("chat: garbage/trivial first reply, retry once")
            retry_msgs = list(base_messages)
            retry_msgs.append({"role": "assistant", "content": reply})
            retry_msgs.append(
                {
                    "role": "user",
                    "content": (
                        "Нужен нормальный ответ по-русски: по смыслу вопроса и по строкам лога в system. "
                        "Без квадратных скобок, без цитирования инструкций, 5–12 предложений."
                    ),
                }
            )
            reply = self.llm.chat(retry_msgs, temperature=retry_temp)
            reply = _plain_text_for_telegram(reply)

        # Всё ещё плохо — отдаём сырые строки лога (без второго LLM)
        if _is_trivial_reply(reply):
            logger.warning("chat: reply still bad after retry, log digest fallback")
            reply = self._fallback_reply_from_log()

        from shared.memory import append_turn

        append_turn(chat_id, "planning", "user", user_message)
        append_turn(chat_id, "planning", "assistant", reply)

        return reply
