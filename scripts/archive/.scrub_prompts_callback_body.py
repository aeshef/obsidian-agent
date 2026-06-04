# git-filter-repo --file-info-callback BODY (not a full def)
STUBS = {
    "config/agent/prompts/finance_intent_router.example.txt": """# Prompt: finance_intent_router
# Prod: config/agent/prompts/finance_intent_router.txt (gitignore)
# Создание: scripts/setup_agent_config.sh
#
# Роль: роутер intent для finance (запись операции vs вопрос по данным vs chitchat).
# Заполните в prod:
# - перечень intent и краткие определения
# - правила: новая операция / аналитика / уточнение к прошлому ответу
# - JSON: {"intent": "...", "reason": "..."}
""",
    "config/agent/prompts/health_tools.example.txt": """# Prompt: health_tools
# Prod: config/agent/prompts/health_tools.txt (gitignore)
#
# Роль: подсказки LLM по health tools (Apple Health / снапшоты).
# Заполните в prod:
# - какие tools вызывать, не угадывать цифры
# - передача day=YYYY-MM-DD
# - поля get_health_series
""",
    "config/agent/prompts/host_domain_router.example.txt": """# Prompt: host_domain_router
# Prod: config/agent/prompts/host_domain_router.txt (gitignore)
#
# Роль: выбор домена unified-бота (finance | planning | knowledge | …).
# Заполните в prod:
# - описание доменов и границ
# - правила при смешанных запросах
# - JSON: domain + reason
""",
    "config/agent/prompts/host_query.example.txt": """# Prompt: host_query (L2 system для unified agent)
# Prod: config/agent/prompts/host_query.txt (gitignore)
#
# Роль: общие правила ассистента, tools, канбан, финансы, знания.
# Заполните в prod (без личных имён/счетов/категорий):
# - тон и язык ответа
# - правила фактов только из tools
# - kanban: колонки, task_id, apply_kanban_task vs get_kanban
# - finance: потребление, переводы, брокер, бейдж (если используете)
""",
    "config/agent/prompts/memory_synth.example.txt": """# Prompt: memory_synth
# Prod: config/agent/prompts/memory_synth.txt (gitignore)
#
# Роль: синтез инсайтов в память агента за период.
# Заполните в prod:
# - что извлекать из логов/контекста
# - формат и лимит длины
# - что не сохранять (PII, разовые детали)
""",
    "config/agent/prompts/planning_intent_router.example.txt": """# Prompt: planning_intent_router
# Prod: config/agent/prompts/planning_intent_router.txt (gitignore)
#
# Роль: роутер intent planning (новая задача vs вопрос/чат).
# Заполните в prod:
# - intent (например task_create, planning_query, chitchat)
# - правила по формулировкам пользователя
# - JSON с intent и reason
""",
    "config/agent/prompts/tool_select_router.example.txt": """# Prompt: tool_select_router
# Prod: config/agent/prompts/tool_select_router.txt (gitignore)
#
# Роль: выбор минимального набора tools по каталогу.
# Заполните в prod:
# - входные поля (domain, message, catalog)
# - когда включать apply_kanban_task / finance / knowledge tools
# - JSON: {"tools": [...], "reason": "..."}
""",
    "finance_bot/config/prompts/amount_extract_prompt.example.txt": """# Prompt: amount_extract_prompt
# Prod: finance_bot/config/prompts/amount_extract_prompt.txt (gitignore)
#
# Роль: извлечь одно число (сумму) из голосового/текстового фрагмента.
# Заполните в prod: примеры форматов, ответ только числом.
""",
    "finance_bot/config/prompts/analyst_prompt.example.txt": """# Prompt: analyst_prompt
# Prod: finance_bot/config/prompts/analyst_prompt.txt (gitignore)
#
# Роль: развёрнутый финансовый анализ периода.
# Заполните в prod:
# - запрет Markdown, тон
# - как читать user_context.md и сводки (переводы, брокер, базлайны)
# - структура ответа (вывод → инсайты → вопрос → шаги)
""",
    "finance_bot/config/prompts/badge_monthly_prompt.example.txt": """# Prompt: badge_monthly_prompt
# Prod: finance_bot/config/prompts/badge_monthly_prompt.txt (gitignore)
#
# Роль: итог месяца по корпоративному бейджу питания (если включён).
# Заполните в prod: правила из badge.yaml rules_context, без Markdown.
""",
    "finance_bot/config/prompts/daily_insight_prompt.example.txt": """# Prompt: daily_insight_prompt
# Prod: finance_bot/config/prompts/daily_insight_prompt.txt (gitignore)
#
# Роль: ежедневный инсайт по данным.
# Заполните в prod: какие метрики сравнивать, тон, запреты.
""",
    "finance_bot/config/prompts/nlu_prompt.example.txt": """# Prompt: nlu_prompt
# Prod: finance_bot/config/prompts/nlu_prompt.txt (gitignore)
#
# Роль: парсинг транзакций из русского текста → JSON.
# Заполните в prod (под свои счета и категории из БД):
# - разрешение дат (occurred_at)
# - сопоставление account / category только из списков пользователя
# - долги, переводы, broker_withdraw, account_balance
# - схема JSON transactions[]
""",
    "finance_bot/config/prompts/plan_parse.example.txt": """# Prompt: plan_parse
# Prod: finance_bot/config/prompts/plan_parse.txt (gitignore)
#
# Роль: извлечь запланированный расход из фразы.
# Заполните в prod:
# - JSON: name, amount, currency, due_month, due_year
# - правила если месяц/год не указаны
""",
    "finance_bot/config/prompts/planning_prompt.example.txt": """# Prompt: planning_prompt
# Prod: finance_bot/config/prompts/planning_prompt.txt (gitignore)
#
# Роль: прогноз / совет по запланированным расходам.
# Заполните в prod: формат JSON или текст, тон.
""",
    "finance_bot/config/prompts/query_prompt.example.txt": """# Prompt: query_prompt
# Prod: finance_bot/config/prompts/query_prompt.txt (gitignore)
#
# Роль: ответ на вопрос пользователя по финансам (чат/аналитика).
# Заполните в prod: факты только из контекста, без Markdown.
""",
    "finance_bot/config/prompts/quick_check_prompt.example.txt": """# Prompt: quick_check_prompt
# Prod: finance_bot/config/prompts/quick_check_prompt.txt (gitignore)
#
# Роль: короткое push-уведомление / быстрая проверка трат.
# Заполните в prod: формат, без Markdown, лимит предложений.
""",
    "finance_bot/config/prompts/summary_prompt.example.txt": """# Prompt: summary_prompt
# Prod: finance_bot/config/prompts/summary_prompt.txt (gitignore)
#
# Роль: краткая суммаризация для рефлексии / отчёта.
# Заполните в prod: период, метрики, тон, длина.
""",
    "knowledge_bot/config/prompts/asr_skip_vision_gate.example.txt": """# Шаблон промпта «asr_skip_vision_gate» (без личных данных)
# Скопируйте в asr_skip_vision_gate.txt и заполните своими инструкциями.
# Файл asr_skip_vision_gate.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/asr_summary.example.txt": """# Шаблон промпта «asr_summary» (без личных данных)
# Скопируйте в asr_summary.txt и заполните своими инструкциями.
# Файл asr_summary.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/field_fill.example.txt": """# Шаблон промпта «field_fill» (без личных данных)
# Скопируйте в field_fill.txt и заполните своими инструкциями.
# Файл field_fill.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/naming.example.txt": """# Шаблон naming.txt — после копирования в naming.txt дополни своими правилами.
# Добавляй конкретику в title (объект, автор, год), чтобы заголовок был узнаваемым при поиске.
# Избегай «Субтитры …» / «Без названия», если есть vision или имя файла.
""",
    "knowledge_bot/config/prompts/ocr_clean.example.txt": """# Шаблон промпта «ocr_clean» (без личных данных)
# Скопируйте в ocr_clean.txt и заполните своими инструкциями.
# Файл ocr_clean.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/query_answer.example.txt": """# Prompt: query_answer
# Prod: knowledge_bot/config/prompts/query_answer.txt (gitignore)
#
# Роль: ответ по полным текстам выбранных заметок.
# Заполните в prod:
# - язык, ссылки на пути заметок
# - запрет выдумывать факты
# - структура для широких запросов
""",
    "knowledge_bot/config/prompts/query_preselect.example.txt": """# Prompt: query_preselect
# Prod: knowledge_bot/config/prompts/query_preselect.txt (gitignore)
# Деплой: sync_to_server.sh / локальный rsync (не из git example как боевой текст).
#
# Роль: первичный отбор заметок по каталогу vault.
# Заполните в prod: критерии релевантности, формат ответа (id/path).
""",
    "knowledge_bot/config/prompts/query_select.example.txt": """# Prompt: query_select
# Prod: knowledge_bot/config/prompts/query_select.txt (gitignore)
#
# Роль: финальный отбор заметок для ответа на вопрос.
# Заполните в prod: вход (вопрос, кандидаты), формат выхода.
""",
    "knowledge_bot/config/prompts/refill_singleton_tags.example.txt": """# Prompt: refill_singleton_tags
# Prod: knowledge_bot/config/prompts/refill_singleton_tags.txt (gitignore)
#
# Роль: согласование редких topic/* на заметке (keep/remove, без новых тегов).
# Заполните в prod:
# - вход: type, body_preview, current_tags_with_counts, rare_tags_on_note
# - правила count>=3, шум vs предметная область
# - JSON: {"tags": [...]}
""",
    "knowledge_bot/config/prompts/routing.example.txt": """# Шаблон промпта «routing» (без личных данных)
# Скопируйте в routing.txt и заполните своими инструкциями.
# Файл routing.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/serendipity_pick.example.txt": """# Шаблон промпта «serendipity_pick» (без личных данных)
# Скопируйте в serendipity_pick.txt и заполните своими инструкциями.
# Файл serendipity_pick.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/tag_ontology_propose.example.txt": """# Шаблон промпта «tag_ontology_propose» (без личных данных)
# Скопируйте в tag_ontology_propose.txt и заполните своими инструкциями.
# Файл tag_ontology_propose.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/tags.example.txt": """# Prompt: tags (онтология тегов vault)
# Prod: knowledge_bot/config/prompts/tags.txt (gitignore)
# На сервере: scripts/ensure_tags_prompt.py создаёт tags.txt при отсутствии.
#
# Заполните в prod:
# - domain / topic / source namespaces и few-shot
# - инвентарь tags_inventory
# - ответ только JSON: {"tags": ["domain/...", "topic/..."]}
# - фраза «json» в тексте обязательна для JSON-mode API
""",
    "knowledge_bot/config/prompts/text_intent.example.txt": """# Шаблон промпта «text_intent» (без личных данных)
# Скопируйте в text_intent.txt и при необходимости подстройте.
# Файл text_intent.txt в git не попадает.
#
# intent=query  — явный поиск/вопрос по уже сохранённым заметкам
# intent=save   — материал для новой заметки
# intent=chat   — приветствие, болтовня, не про поиск в vault
""",
    "knowledge_bot/config/prompts/title.example.txt": """# Шаблон промпта «title» (без личных данных)
# Скопируйте в title.txt и заполните своими инструкциями.
# Файл title.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/vision.example.txt": """# Шаблон промпта «vision» (без личных данных)
# Скопируйте в vision.txt и заполните своими инструкциями.
# Файл vision.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/wikilinks_select.example.txt": """# Шаблон промпта «wikilinks_select» (без личных данных)
# Скопируйте в wikilinks_select.txt и заполните своими инструкциями.
# Файл wikilinks_select.txt в git не попадает.
""",
    "knowledge_bot/config/prompts/yt_transcript_summary.example.txt": """# Шаблон промпта «yt_transcript_summary» (без личных данных)
# Скопируйте в yt_transcript_summary.txt и заполните своими инструкциями.
# Файл yt_transcript_summary.txt в git не попадает.
""",
    "planning_bot/config/prompts/calendar_week_insights.example.txt": """# Шаблон промпта «calendar_week_insights» (без личных данных)
# Скопируйте в calendar_week_insights.txt и заполните своими инструкциями.
# Файл calendar_week_insights.txt в git не попадает.
""",
    "planning_bot/config/prompts/conversation.example.txt": """# Prompt: conversation
# Prod: planning_bot/config/prompts/conversation.txt (gitignore)
#
# Роль: свободный чат planning-бота.
# Заполните в prod:
# - факты только из контекста/tools
# - даты → day=YYYY-MM-DD для tools
# - стиль ответа (без markdown-заголовков)
""",
    "planning_bot/config/prompts/goals_mapping.example.txt": """# Шаблон промпта «goals_mapping» (без личных данных)
# Скопируйте в goals_mapping.txt и заполните своими инструкциями.
# Файл goals_mapping.txt в git не попадает.
""",
    "planning_bot/config/prompts/intent_router.example.txt": """# Шаблон промпта «intent_router» (без личных данных)
# Скопируйте в intent_router.txt и заполните своими инструкциями.
# Файл intent_router.txt в git не попадает.
""",
    "planning_bot/config/prompts/iphone_health_insights.example.txt": """# Устарело: используйте config/agent/prompts/health_tools.txt для agent и health-инструментов.
""",
    "planning_bot/config/prompts/recommendations.example.txt": """# Шаблон промпта «recommendations» (без личных данных)
# Скопируйте в recommendations.txt и заполните своими инструкциями.
# Файл recommendations.txt в git не попадает — на сервер копируется rsync с локальной машины.
#
# Обязательные плейсхолдеры для .format() в коде (см. core/llm.py → generate_recommendations):
#   {current_date_iso}   — например 2026-05-06
#   {current_date_ru}    — например «6 мая 2026 г.»
#   {current_time_msk}
#   {day_of_week}
#   {is_weekend}
""",
    "planning_bot/config/prompts/routines_recommendations.example.txt": """# Шаблон промпта «routines_recommendations» (без личных данных)
# Скопируйте в routines_recommendations.txt и заполните своими инструкциями.
# Файл routines_recommendations.txt в git не попадает.
""",
    "planning_bot/config/prompts/task_parsing.example.txt": """# Шаблон промпта «task_parsing» (без личных данных)
# Скопируйте в task_parsing.txt и заполните своими инструкциями.
# Файл task_parsing.txt в git не попадает.
""",
    "planning_bot/config/prompts/weekly_review.example.txt": """# Шаблон промпта «weekly_review» (без личных данных)
# Скопируйте в weekly_review.txt и заполните своими инструкциями.
# Файл weekly_review.txt в git не попадает.
""",
}


try:
    _fn = filename.decode("utf-8")
except Exception:
    _fn = filename.decode("utf-8", "surrogateescape")
_is_prompt = (
    (_fn.endswith(".example.txt") or _fn.endswith(".txt"))
    and ("/config/prompts/" in _fn or _fn.startswith("config/agent/prompts/"))
)
if not _is_prompt:
    return (filename, mode, blob_id)
_text = STUBS.get(_fn) or (
    "# Prompt: "
    + _fn.split("/")[-1].replace(".example.txt", "").replace(".txt", "")
    + "\n# Redacted from git history.\n"
)
blob_id = value.insert_file_with_contents(_text.encode("utf-8"))
return (filename, mode, blob_id)
