"""Интеграция с DeepSeek API.

HTTP-транспорт — shared.llm.LLMClient; здесь — retry, доменные методы (parse_task, weekly review и т.д.).
Публичный API DeepSeekClient.chat(messages) не менялся.
"""
import re
import requests
import json
import logging
import traceback
from typing import Dict, List, Optional
from time import sleep

from shared.constants import deepseek_base_url
from shared.llm import LLMClient as _SharedLLMClient

from .config import DEEPSEEK_API_TOKEN, DEEPSEEK_API_URL, DEEPSEEK_MODEL
from .settings import load_prompt, get_config_path

logger = logging.getLogger(__name__)


def _strip_telegram_markdown_facade(text: str) -> str:
    """Убирает типичный Markdown, который в обычном Telegram выглядит как мусор (** не жирнит)."""
    if not text:
        return text
    out = text.replace("**", "").replace("__", "")
    out = re.sub(r"(?m)^#{1,6}\s+", "", out)
    out = out.replace("`", "")
    return out


def _append_mac_iphone_context_for_recommendations(context: str) -> str:
    """Те же источники, что в чате (сегодня) и в еженедельном ревью (неделя): Mac + iPhone."""
    parts: List[str] = []

    try:
        from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_TODAY_JSON
        from planning_bot.services.context_parser import (
            format_for_llm,
            get_today_snapshot,
            load_chat_snapshot_from_json,
        )

        snap = load_chat_snapshot_from_json(CONTEXT_TODAY_JSON)
        if not snap:
            snap = get_today_snapshot(CONTEXT_MAC_DIR, logging_window_only=True)
        mac_today = format_for_llm(snap)
        if mac_today:
            parts.append(mac_today)
    except Exception as e:
        logger.debug("recommendations Mac today: %s", e)

    try:
        from planning_bot.core.config import IPHONE_CONTEXT_DIR
        from planning_bot.services.iphone_context_parser import (
            format_for_llm as iphone_format_for_llm,
            get_latest_snapshot,
        )

        iphone_snap = get_latest_snapshot(IPHONE_CONTEXT_DIR)
        iphone_str = iphone_format_for_llm(iphone_snap)
        if iphone_str:
            parts.append(iphone_str)
    except Exception as e:
        logger.debug("recommendations iPhone latest: %s", e)

    try:
        from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_WEEK_JSON
        from planning_bot.services.context_parser import format_week_stats_for_llm, get_snapshots

        mac_snaps = get_snapshots(CONTEXT_MAC_DIR, days=7, logging_window_only=True)
        if not mac_snaps and CONTEXT_WEEK_JSON.exists():
            raw = json.loads(CONTEXT_WEEK_JSON.read_text(encoding="utf-8"))
            mac_snaps = raw.get("snapshots") or []
        mac_week = format_week_stats_for_llm(mac_snaps)
        if mac_week:
            parts.append(mac_week)
    except Exception as e:
        logger.debug("recommendations Mac week: %s", e)

    try:
        from planning_bot.core.config import IPHONE_CONTEXT_DIR
        from planning_bot.services.iphone_context_parser import (
            format_week_stats_for_llm as iphone_week_stats,
            get_week_snapshots,
        )

        iphone_snaps = get_week_snapshots(IPHONE_CONTEXT_DIR)
        iphone_week = iphone_week_stats(iphone_snaps)
        if iphone_week:
            parts.append(iphone_week)
    except Exception as e:
        logger.debug("recommendations iPhone week: %s", e)

    if not parts:
        return context
    block = "=== Mac / iPhone (факты о дне и неделе; не календарь) ===\n" + "\n\n".join(parts)
    return context + "\n\n" + block


class APITimeoutError(Exception):
    """Специфичное исключение для тайм-аутов API"""
    pass


class DeepSeekClient:
    def __init__(self):
        if not DEEPSEEK_API_TOKEN:
            raise ValueError("DEEPSEEK_API_TOKEN не установлен в переменных окружения")
        self.api_token = DEEPSEEK_API_TOKEN
        self.api_url = DEEPSEEK_API_URL
        self.model = DEEPSEEK_MODEL
        self._transport = _SharedLLMClient(
            api_key=DEEPSEEK_API_TOKEN,
            base_url=deepseek_base_url(override=DEEPSEEK_API_URL),
            model=DEEPSEEK_MODEL,
        )

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_retries: int = 3) -> str:
        """Отправка запроса в DeepSeek API с retry логикой (транспорт — shared.llm)."""
        logger.info("📤 Отправка запроса к DeepSeek API")
        logger.debug("Model: %s, Temperature: %s, messages: %s", self.model, temperature, len(messages))

        for attempt in range(1, max_retries + 1):
            try:
                logger.info("🔄 Попытка %s/%s", attempt, max_retries)
                content = self._transport.chat_messages(
                    messages,
                    temperature=temperature,
                    timeout=90.0,
                    raise_on_error=True,
                )
                logger.info("✅ Успешный ответ от API (длина: %s символов)", len(content))
                logger.debug("Response preview: %s...", content[:200])
                return content

            except requests.exceptions.Timeout as e:
                logger.error(f"⏱️ Таймаут на попытке {attempt}/{max_retries}")
                logger.error(f"Timeout error: {str(e)}")
                logger.error(f"URL: {self.api_url}")
                if attempt < max_retries:
                    wait_time = attempt * 2
                    logger.info(f"⏳ Ожидание {wait_time} секунд перед повтором...")
                    sleep(wait_time)
                else:
                    logger.error(f"❌ Все попытки исчерпаны. Последняя ошибка: {traceback.format_exc()}")
                    raise APITimeoutError(f"Таймаут при запросе к DeepSeek API после {max_retries} попыток. API не отвечает в течение 90 секунд. Проверьте подключение к интернету или попробуйте позже.")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Ошибка запроса на попытке {attempt}/{max_retries}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                logger.error(f"URL: {self.api_url}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response length: {len(e.response.text)} chars (body not logged)")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                
                if attempt < max_retries:
                    wait_time = attempt * 2
                    logger.info(f"⏳ Ожидание {wait_time} секунд перед повтором...")
                    sleep(wait_time)
                else:
                    raise Exception(f"Ошибка при запросе к DeepSeek API после {max_retries} попыток: {e}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"❌ Ошибка парсинга JSON ответа")
                logger.error(f"Response length: {len(response.text) if 'response' in locals() else 0} chars (body not logged)")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                raise Exception(f"Ошибка парсинга JSON ответа от DeepSeek API: {e}")
                
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка на попытке {attempt}/{max_retries}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                if attempt < max_retries:
                    wait_time = attempt * 2
                    logger.info(f"⏳ Ожидание {wait_time} секунд перед повтором...")
                    sleep(wait_time)
                else:
                    raise Exception(f"Неожиданная ошибка при запросе к DeepSeek API: {e}")

    def parse_task(self, user_message: str, context: Optional[Dict] = None) -> Dict[str, str]:
        """Парсинг задачи из естественного языка с помощью LLM"""
        logger.info(f"🔍 Парсинг задачи: {user_message[:100]}...")
        
        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "task_parsing")
            logger.debug(f"Загружен промпт для парсинга задач (длина: {len(system_prompt)} символов)")

            context_text = ""
            if context:
                if context.get("recent_tasks"):
                    context_text += f"\n\nНедавние задачи пользователя:\n"
                    for task in context["recent_tasks"][:5]:
                        context_text += f"- {task}\n"
                    logger.debug(f"Добавлен контекст: {len(context.get('recent_tasks', []))} недавних задач")
                if context.get("goals"):
                    context_text += f"\n\nАктуальные цели:\n"
                    for goal in context["goals"][:5]:
                        context_text += f"- {goal}\n"
                    logger.debug(f"Добавлен контекст: {len(context.get('goals', []))} целей")
                if context.get("upcoming_events"):
                    context_text += f"\n\n{context['upcoming_events']}"
                    logger.debug("Добавлен контекст календаря в парсинг задачи")

            messages = [
                {"role": "system", "content": system_prompt + context_text},
                {"role": "user", "content": user_message}
            ]

            response = self.chat(messages, temperature=0.3)
            logger.debug(f"Получен ответ от LLM для парсинга (длина: {len(response)} символов)")
            
            # Парсим JSON из ответа
            try:
                # Убираем markdown код блоки если есть
                original_response = response
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0].strip()
                
                result = json.loads(response)
                parsed = {
                    "title": result.get("title", user_message),
                    "category": result.get("category", "дом"),
                    "priority": result.get("priority", "средний")
                }
                logger.info(f"✅ Задача распарсена: {parsed}")
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Не удалось распарсить JSON ответа: {e}")
                logger.debug(f"Ответ LLM: {original_response[:500]}")
                logger.info(f"Используются дефолтные значения")
                # Если не удалось распарсить, возвращаем дефолтные значения
                return {
                    "title": user_message,
                    "category": "дом",
                    "priority": "средний"
                }
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге задачи: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise

    def generate_weekly_review(
        self,
        weekly_stats: Dict,
        goals: List[str],
        quarterly_focus: List[str],
        goals_context: Optional[str] = None,
        previous_reflections: Optional[str] = None,
        weekly_logs: Optional[str] = None,
        weekly_moves: Optional[List[Dict]] = None,
        calendar_events: Optional[str] = None,
    ) -> str:
        """Генерация еженедельного ревью"""
        logger.info("📝 Генерация еженедельного ревью")
        logger.debug(f"Статистика: {weekly_stats}")
        logger.debug(f"Целей: {len(goals)}, Квартальных фокусов: {len(quarterly_focus)}")
        
        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "weekly_review")
            logger.debug(f"Загружен промпт для еженедельного ревью (длина: {len(system_prompt)} символов)")

            from datetime import datetime, timedelta
            now = datetime.now()
            today = now.date()
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=6)
            week_start_str = week_start.strftime("%d.%m")
            week_end_str = week_end.strftime("%d.%m")
            formed_at_str = today.strftime("%d.%m.%Y")
            weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
            weekday_str = weekday_names[today.weekday()]
            time_str = now.strftime("%H:%M")

            completed = weekly_stats.get("completed", 0)
            completed_list = weekly_stats.get("completed_this_week_list") or []
            backlog_only = weekly_stats.get("backlog_only", 0)
            in_work = weekly_stats.get("in_work", 0)
            total_active = weekly_stats.get("total_active", weekly_stats.get("backlog_size", 0))
            in_blocked = weekly_stats.get("in_blocked", 0)
            in_waiting_date = weekly_stats.get("in_waiting_date", 0)
            in_postponed = weekly_stats.get("in_postponed", 0)
            num_moves = len(weekly_moves) if weekly_moves else 0

            completed_titles_block = ""
            if completed_list:
                lines = []
                for t in completed_list[:80]:
                    title = (t.get("title") or "").strip()
                    if not title:
                        continue
                    cat = t.get("category") or ""
                    lines.append(f"- {title}" + (f" ({cat})" if cat else ""))
                completed_titles_block = "\nСписок завершённых за неделю (название и категория):\n" + "\n".join(lines)
                if len(completed_list) > 80:
                    completed_titles_block += f"\n... и ещё {len(completed_list) - 80} задач."

            stats_text = f"""Данные для ревью (используй ТОЛЬКО эти числа и списки в анализе).

Неделя: понедельник {week_start_str} — воскресенье {week_end_str}.
Дата и время формирования: {weekday_str}, {formed_at_str}, {time_str}. Все упоминания «сегодня», «завтра», «вечер» — относительно этой даты и времени.

Текущее состояние доски (на момент формирования):
- Колонка «📋 Бэклог»: {backlog_only} задач
- Колонка «📅 Ждёт даты»: {in_waiting_date} задач
- Колонка «⏸ Отложено»: {in_postponed} задач
- Колонка «🔄 В работе»: {in_work} задач (только эта колонка = «в работе», не путай с другими)
- Колонка «🚫 Заблокировано»: {in_blocked} задач
- Всего активных (только Бэклог + В работе): {total_active}

За неделю (пн–вс) по логам:
- Выполнено за неделю: {completed}
- Записей о перемещениях в списке ниже: {num_moves}

Разбивка выполненных по категориям: {weekly_stats.get('by_category', {})}
Разбивка выполненных по приоритетам: {weekly_stats.get('by_priority', {})}
{completed_titles_block}

Важно: «В работе» — только колонка «🔄 В работе». Активные для планирования — только «📋 Бэклог» и «🔄 В работе». «📅 Ждёт даты», «⏸ Отложено», «🚫 Заблокировано» — отдельные колонки. Ссылайся на конкретные задачи из списка завершённых и из перемещений — это делает ревью живым и полезным."""

            goals_text = "\n\nГодовые цели:\n" + "\n".join(f"- {goal}" for goal in goals[:10])
            
            focus_text = "\n\nКвартальные фокусы:\n" + "\n".join(f"- {goal}" for goal in quarterly_focus[:10])

            context_text = stats_text + goals_text + focus_text

            if calendar_events:
                context_text += (
                    "\n\n=== КАЛЕНДАРЬ (фактические встречи в окне дат; не выдумывай встреч сверх этого блока) ===\n"
                    + calendar_events.strip()
                )
                logger.debug("Календарь в ревью: да (%d символов)", len(calendar_events))

            # Mac-контекст за неделю (приложения, фокус-режимы); окно 10:00–02:00
            try:
                import json

                from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_WEEK_JSON
                from planning_bot.services.context_parser import format_week_stats_for_llm, get_snapshots

                mac_snaps = get_snapshots(CONTEXT_MAC_DIR, days=7, logging_window_only=True)
                if not mac_snaps and CONTEXT_WEEK_JSON.exists():
                    raw = json.loads(CONTEXT_WEEK_JSON.read_text(encoding="utf-8"))
                    mac_snaps = raw.get("snapshots") or []
                mac_week = format_week_stats_for_llm(mac_snaps)
                if mac_week:
                    context_text += "\n\n" + mac_week
                    logger.debug("Контекст Mac в ревью: %d снапшотов", len(mac_snaps))
            except Exception as _e:
                logger.debug("Контекст Mac для ревью недоступен: %s", _e)

            # iPhone-контекст за неделю (здоровье, шаги, питание)
            try:
                from planning_bot.core.config import IPHONE_CONTEXT_DIR
                from planning_bot.services.iphone_context_parser import (
                    format_week_stats_for_llm as iphone_week_stats,
                    get_week_snapshots,
                )

                iphone_snaps = get_week_snapshots(IPHONE_CONTEXT_DIR)
                iphone_week = iphone_week_stats(iphone_snaps)
                if iphone_week:
                    context_text += "\n\n" + iphone_week
                    logger.debug("iPhone-контекст в ревью: %d снапшотов", len(iphone_snaps))
            except Exception as _e:
                logger.debug("iPhone-контекст для ревью недоступен: %s", _e)

            if weekly_moves:
                max_moves = 400
                moves_block = "\n\nПеремещения за неделю (хронологический порядок; опирайся только на эти строки):\n"
                for ev in weekly_moves[:max_moves]:
                    moves_block += f"- {ev.get('timestamp', '')} | \"{ev.get('title', '')}\" | {ev.get('from', '')} → {ev.get('to', '')}\n"
                if len(weekly_moves) > max_moves:
                    moves_block += f"... и ещё {len(weekly_moves) - max_moves} записей (всего {len(weekly_moves)}).\n"
                context_text += moves_block
                logger.debug(f"Добавлены перемещения за неделю: {len(weekly_moves)} записей")

            if goals_context:
                context_text += f"\n\nКонтекст целей (почему они важны):\n{goals_context}"
                logger.debug(f"Добавлен контекст целей ({len(goals_context)} символов)")
            
            if previous_reflections:
                context_text += f"\n\nКонтекст из предыдущих рефлексий:\n{previous_reflections[:1000]}"
                logger.debug(f"Добавлен контекст рефлексий ({len(previous_reflections)} символов)")
            
            if weekly_logs:
                context_text += f"\n\nИстория действий за неделю (создания, перемещения, завершения):\n{weekly_logs}"
                logger.debug(f"Добавлена история действий ({len(weekly_logs)} символов)")

            logger.debug(f"Общий размер контекста: {len(context_text)} символов")
            # Для отладки: что именно ушло в ревью (модель не получает список задач, только агрегаты — отсюда «вероятно» в ответах)
            user_content = (
                "Сгенерируй еженедельный ревью по данным ниже. Все цифры в анализе должны совпадать с блоком «Данные для ревью»; "
                "при описании перемещений используй только строки из списка «Перемещения за неделю». "
                "Если есть блок «КАЛЕНДАРЬ» — обязательно вплети его в анализ: назови 1–2 самых плотных дня по датам и встречам из этого блока "
                "и свяжи с глубокой работой/отдыхом; не описывай календарь, которого нет во входе.\n\n"
                + context_text
            )
            logger.info(
                "📋 Ревью контекст: system=%d | calendar=%s | goals_context=%s | previous_reflections=%s | weekly_logs=%s | user=%d символов",
                len(system_prompt),
                "да" if calendar_events else "нет",
                "да" if goals_context else "нет",
                "да" if previous_reflections else "нет",
                "да" if weekly_logs else "нет",
                len(user_content),
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]

            review = self.chat(messages, temperature=0.8)
            logger.info(f"✅ Еженедельное ревью сгенерировано (длина: {len(review)} символов)")
            return review
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации еженедельного ревью: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise

    def generate_recommendations(
        self,
        tasks: List[Dict],
        goals: List[str],
        weekly_stats: Dict,
        goals_context: Optional[str] = None,
        identity_summary: Optional[str] = None,
        weekly_logs: Optional[str] = None,
        tasks_mapping: Optional[Dict] = None,
        tasks_history: Optional[Dict[str, str]] = None,
        calendar_context: Optional[str] = None,
    ) -> str:
        """Генерация умных рекомендаций"""
        from datetime import datetime, timezone, timedelta

        logger.info(f"💡 Генерация рекомендаций для {len(tasks)} задач")

        _months_ru = (
            "",
            "января",
            "февраля",
            "марта",
            "апреля",
            "мая",
            "июня",
            "июля",
            "августа",
            "сентября",
            "октября",
            "ноября",
            "декабря",
        )

        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "recommendations")

            try:
                from zoneinfo import ZoneInfo

                msk_tz = ZoneInfo("Europe/Moscow")
            except Exception:
                msk_tz = timezone(timedelta(hours=3))
            now_msk = datetime.now(msk_tz)
            current_time_msk = now_msk.strftime("%H:%M")
            anchor_date = now_msk.date()
            current_date_iso = anchor_date.isoformat()
            current_date_ru = (
                f"{anchor_date.day} {_months_ru[anchor_date.month]} {anchor_date.year} г."
            )
            day_of_week = now_msk.strftime("%A")
            day_names_ru = {
                'Monday': 'Понедельник',
                'Tuesday': 'Вторник',
                'Wednesday': 'Среда',
                'Thursday': 'Четверг',
                'Friday': 'Пятница',
                'Saturday': 'Суббота',
                'Sunday': 'Воскресенье'
            }
            day_of_week_ru = day_names_ru.get(day_of_week, day_of_week)
            is_weekend = "Выходной" if now_msk.weekday() >= 5 else "Будний день"
            
            # Подставляем время, календарную дату и день недели в промпт
            system_prompt = system_prompt.format(
                current_time_msk=current_time_msk,
                day_of_week=day_of_week_ru,
                is_weekend=is_weekend,
                current_date_iso=current_date_iso,
                current_date_ru=current_date_ru,
            )

            logger.debug(f"Загружен промпт для рекомендаций (длина: {len(system_prompt)} символов)")
            logger.debug(
                "Время МСК: %s, дата якорь: %s, День: %s, %s",
                current_time_msk,
                current_date_iso,
                day_of_week_ru,
                is_weekend,
            )

            # Формируем список задач с полной информацией
            tasks_text = []
            # Разделяем задачи по колонкам
            in_work_tasks = []
            backlog_tasks = []
            
            # Логируем детали всех задач
            logger.info(f"📋 ВСЕГО задач получено: {len(tasks)}")
            for idx, t in enumerate(tasks[:5], 1):  # Логируем первые 5 для примера
                logger.info(f"  {idx}. '{t.get('title', '')[:50]}...' | Колонка: '{t.get('column', 'None')}' | ID: {t.get('task_id', 'нет')}")
            
            for t in tasks:
                task_dict = {
                    "task": t,
                    "column": t.get('column', '📋 Бэклог'),
                    "title": t.get('title', ''),
                    "category": t.get('category', ''),
                    "priority": t.get('priority', ''),
                    "created_date": t.get('created_date', ''),
                    "deadline": t.get('deadline'),
                    "task_id": t.get('task_id')
                }
                
                column = t.get('column') or '📋 Бэклог'
                logger.debug(f"Задача '{t.get('title', '')[:40]}...' в колонке: '{column}'")
                
                if column == "🔄 В работе":
                    in_work_tasks.append(task_dict)
                    logger.info(f"✅ Найдена задача 'В работе': '{t.get('title', '')[:50]}...'")
                else:
                    backlog_tasks.append(task_dict)
            
            logger.info(f"📊 РАЗДЕЛЕНИЕ: {len(in_work_tasks)} задач 'В работе', {len(backlog_tasks)} задач в бэклоге")
            
            # Формируем текст для задач "В работе" (они важнее)
            if in_work_tasks:
                tasks_text.append("=== ЗАДАЧИ В РАБОТЕ (приоритет!) ===")
                for td in in_work_tasks:
                    t = td["task"]
                    task_line = f"- {td['title']}"
                    task_line += f" [Категория: {td['category']}, Приоритет: {td['priority']}]"
                    if td['created_date']:
                        task_line += f" | Создана: {td['created_date']}"
                    if td.get('deadline'):
                        task_line += f" | ⚠️ Дедлайн: {td['deadline']}"
                    
                    # Добавляем историю перемещений
                    if tasks_history and td['title'] in tasks_history:
                        task_line += f" | История: {tasks_history[td['title']]}"
                    
                    # Добавляем связанные цели
                    task_id = td['task_id']
                    if tasks_mapping and task_id and task_id in tasks_mapping:
                        related_goals = tasks_mapping[task_id]
                        if related_goals:
                            goals_text = ", ".join([g.get('text', '')[:40] for g in related_goals[:2]])
                            task_line += f" | → Цели: {goals_text}"
                    
                    tasks_text.append(task_line)
                tasks_text.append("")
            
            # Формируем текст для задач из бэклога
            if backlog_tasks:
                tasks_text.append("=== ЗАДАЧИ В БЭКЛОГЕ ===")
                for td in backlog_tasks:
                    t = td["task"]
                    task_line = f"- {td['title']}"
                    task_line += f" [Категория: {td['category']}, Приоритет: {td['priority']}]"
                    if td['created_date']:
                        task_line += f" | Создана: {td['created_date']}"
                    if td.get('deadline'):
                        task_line += f" | ⚠️ Дедлайн: {td['deadline']}"
                    
                    # Добавляем историю перемещений
                    if tasks_history and td['title'] in tasks_history:
                        task_line += f" | История: {tasks_history[td['title']]}"
                    
                    # Добавляем связанные цели
                    task_id = td['task_id']
                    if tasks_mapping and task_id and task_id in tasks_mapping:
                        related_goals = tasks_mapping[task_id]
                        if related_goals:
                            goals_text = ", ".join([g.get('text', '')[:40] for g in related_goals[:2]])
                            task_line += f" | → Цели: {goals_text}"
                    
                    tasks_text.append(task_line)
            
            tasks_text_str = "\n".join(tasks_text)
            
            # Логируем, что передается в промпт
            logger.info(f"📝 Текст задач для промпта ({len(tasks_text)} строк):")
            logger.info(f"--- НАЧАЛО ТЕКСТА ЗАДАЧ ---")
            logger.info(tasks_text_str[:500] + "..." if len(tasks_text_str) > 500 else tasks_text_str)
            logger.info(f"--- КОНЕЦ ТЕКСТА ЗАДАЧ ---")
            
            # Добавляем статистику по колонкам
            stats_summary = f"""Активных задач всего: {len(tasks)}
Задач в работе: {len(in_work_tasks)} (ВЫСШИЙ ПРИОРИТЕТ - уже начаты!)
Задач в бэклоге: {len(backlog_tasks)}
"""
            logger.info(f"📊 СТАТИСТИКА ДЛЯ ПРОМПТА: {stats_summary.strip()}")

            context = f"""ТЕКУЩИЕ ЗАДАЧИ (ВСЕ активные задачи):
{stats_summary}
{tasks_text_str}

СТАТИСТИКА ЗА НЕДЕЛЮ: {weekly_stats}

ЦЕЛИ: {', '.join(goals[:5])}"""
            
            if goals_context:
                context += f"\n\nКонтекст целей:\n{goals_context}"
                logger.debug(f"Добавлен контекст целей ({len(goals_context)} символов)")
            
            if identity_summary:
                context += f"\n\nКонтекст идентичности: {identity_summary[:500]}"
                logger.debug(f"Добавлен контекст идентичности ({len(identity_summary)} символов)")
            
            if weekly_logs:
                context += f"\n\nИстория действий за неделю:\n{weekly_logs}"
                logger.debug(f"Добавлена история действий ({len(weekly_logs)} символов)")

            if calendar_context:
                context += f"\n\nКАЛЕНДАРЬ (реальные встречи; учитывай свободные окна и перегруз по времени):\n{calendar_context}"
                logger.debug("Добавлен контекст календаря в рекомендации")

            context = _append_mac_iphone_context_for_recommendations(context)

            logger.debug(f"Общий размер контекста: {len(context)} символов")

            anchor_hint = (
                f"Якорная дата и время (МСК), единственный ориентир для «сегодня», «завтра» и просроченных дедлайнов: "
                f"{current_date_ru} ({current_date_iso}), {current_time_msk}. "
                f"Сверяй поля «⚠️ Дедлайн:» с датой {current_date_iso}."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{anchor_hint}\n\nДай рекомендации на основе:\n{context}"},
            ]

            recommendations = self.chat(messages, temperature=0.7)
            recommendations = _strip_telegram_markdown_facade((recommendations or "").strip())
            logger.info(f"✅ Рекомендации сгенерированы (длина: {len(recommendations)} символов)")
            return recommendations
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации рекомендаций: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise
    
    def map_task_to_goals(self, task_title: str, task_category: str, goals_list: List[Dict]) -> Dict:
        """Маппинг задачи к квартальным целям через LLM"""
        logger.info(f"🔗 Маппинг задачи к целям: {task_title[:50]}...")
        
        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "goals_mapping")
            
            # Формируем список целей — ВСЕ цели (без лимита)
            goals_text = "Доступные цели (используй ТОЛЬКО эти ID!):\n"
            for goal in goals_list:
                goal_id = goal.get("id", "")
                goal_text = goal.get("text", "")
                goal_quarter = goal.get("quarter", "")
                goal_category = goal.get("category", "")
                goal_priority = goal.get("priority", "")
                goals_text += f"ID: {goal_id} | {goal_text} | Категория: {goal_category} | Квартал: {goal_quarter} | Приоритет: {goal_priority}\n"
            
            messages = [
                {"role": "system", "content": system_prompt + f"\n\nДоступные цели:\n{goals_text}"},
                {"role": "user", "content": f"Задача: {task_title}\nКатегория: {task_category}"}
            ]
            
            response = self.chat(messages, temperature=0.3)
            
            # Парсим JSON
            try:
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0].strip()
                
                result = json.loads(response)
                return {
                    "goal_ids": result.get("goal_ids", []),
                    "reasoning": result.get("reasoning", "")
                }
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка при парсинге JSON маппинга: {e}")
                logger.error(f"Ответ LLM: {response}")
                return {"goal_ids": [], "reasoning": "Ошибка парсинга"}
                
        except Exception as e:
            logger.error(f"Ошибка при маппинге задачи к целям: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"goal_ids": [], "reasoning": f"Ошибка: {e}"}