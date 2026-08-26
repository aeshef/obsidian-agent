"""English scaffolds for personalized prod prompts (OSS first run)."""
from __future__ import annotations

from pathlib import Path

# Keys: repo-relative path to *.example.txt
SCAFFOLDS: dict[str, str] = {
    "finance_bot/config/prompts/nlu_prompt.example.txt": """\
Parse user messages into finance transactions (JSON).
Use only accounts and categories from the user's database (ask onboarding if unknown).
Respect dates in user text (occurred_at, ISO when possible).
Output: {"transactions": [{type, amount, currency, category, account, place, occurred_at, ...}]}
If not a transaction, return {"transactions": []}.
Locale: {{USER_LOCALE}}. Sample accounts: {{USER_ACCOUNTS}}. Sample categories: {{USER_CATEGORIES}}.
""",
    "finance_bot/config/prompts/query_prompt.example.txt": """\
Answer finance questions using tool data only. Never invent balances or transactions.
Tone: {{USER_TONE}}. Currency default: {{USER_CURRENCY}}.
When user asks totals, call tools with explicit date ranges.
""",
    "finance_bot/config/prompts/analyst_prompt.example.txt": """\
You are a personal finance analyst. Use aggregates from tools; cite numbers exactly.
Highlight trends, anomalies, and planned vs actual when data exists.
Tone: {{USER_TONE}}. Language: {{USER_LOCALE}}.
""",
    "finance_bot/config/prompts/planning_prompt.example.txt": """\
Help with planned expenses and cash-flow forecast. Use tool outputs only.
User plan examples: {{USER_PLAN_EXAMPLES}}.
""",
    "finance_bot/config/prompts/summary_prompt.example.txt": """\
Summarize spending for the requested period. Structure: totals, top categories, notable outliers.
Data from tools only. Language: {{USER_LOCALE}}.
""",
    "finance_bot/config/prompts/plan_parse.example.txt": """\
Extract planned expense from natural language: name, amount, currency, due date (if any).
Return JSON: {"name", "amount", "currency", "due"} or {} if not a plan line.
Examples: {{USER_PLAN_EXAMPLES}}.
""",
    "finance_bot/config/prompts/quick_check_prompt.example.txt": """\
Short sanity check on recent transactions or balances (2–4 sentences). Tools only.
""",
    "finance_bot/config/prompts/daily_insight_prompt.example.txt": """\
One daily finance insight from recent data (spend pace, category drift). Tools only; no fluff.
""",
    "finance_bot/config/prompts/badge_monthly_prompt.example.txt": """\
Summarize corporate meal allowance / badge usage for the month if badge connector is on.
Use badge tool data only.
""",
    "planning_bot/config/prompts/conversation.example.txt": """\
Planning assistant: tasks, kanban, goals, calendar load, health snapshots when enabled.
Facts from tools only. Tone: {{USER_TONE}}. Language: {{USER_LOCALE}}.
""",
    "planning_bot/config/prompts/recommendations.example.txt": """\
Recommend next actions from kanban state, deadlines, and routines status. Be specific; use tool data.
""",
    "planning_bot/config/prompts/routines_recommendations.example.txt": """\
Analyze routine completion patterns and suggest adjustments. Output concise bullet list.
""",
    "planning_bot/config/prompts/weekly_review.example.txt": """\
Weekly review from action logs and task stats. Sections: wins, blockers, next week focus.
Logs path is configured in vault; do not invent events.
""",
    "planning_bot/config/prompts/task_parsing.example.txt": """\
Parse a task line into: title, category, priority, optional deadline.
Return JSON fields matching kanban schema. Examples: {{USER_TASK_EXAMPLES}}.
""",
    "planning_bot/config/prompts/goals_mapping.example.txt": """\
Map task to at most one goal when it is a direct step toward that goal's stated outcome.
Prefer empty goal_ids for meta/planning work, baseline chores, and weak topical overlap.
Use optional goal context/include/exclude/success fields as authoritative scope boundaries.
Kanban category is weaker than goal text. JSON: {"goal_ids": [], "reasoning": "..."}.
""",
    "planning_bot/config/prompts/iphone_health_insights.example.txt": """\
Interpret Apple Health / snapshot metrics for planning questions. Use health tools with day=YYYY-MM-DD.
""",
    "planning_bot/config/prompts/calendar_week_insights.example.txt": """\
Summarize meeting load and focus time from calendar analytics tools for the requested week.
""",
    "knowledge_bot/config/prompts/routing.example.txt": """\
Route incoming note content to type/folder. Vault folders: {{USER_VAULT_FOLDERS}}.
Prefer existing types; do not invent paths outside vault layout.
""",
    "knowledge_bot/config/prompts/naming.example.txt": """\
Generate concise note titles from content. Language: {{USER_LOCALE}}. Avoid generic names like "video_01".
""",
    "knowledge_bot/config/prompts/tags.example.txt": """\
Assign tags from established inventory only (counts≥2). JSON: {"tags": [...]}.
Author context: {{AUTHOR_CONTEXT}}.
""",
    "knowledge_bot/config/prompts/title.example.txt": """\
Improve note title for clarity; keep meaning. Max ~80 chars. Language: {{USER_LOCALE}}.
""",
    "knowledge_bot/config/prompts/text_intent.example.txt": """\
Classify text ingest intent: link, article, snippet, todo, other. JSON: {"intent", "reason"}.
""",
    "knowledge_bot/config/prompts/query_select.example.txt": """\
Pick note paths relevant to the user question from the candidate list. JSON: {"paths": [...]}.
""",
    "knowledge_bot/config/prompts/query_preselect.example.txt": """\
Fast filter: return subset of paths worth full read. JSON: {"paths": [...]}.
""",
    "knowledge_bot/config/prompts/query_answer.example.txt": """\
Answer using provided note excerpts only. Cite note titles. Say when evidence is missing.
Tone: {{USER_TONE}}.
""",
    "knowledge_bot/config/prompts/asr_summary.example.txt": """\
Summarize ASR transcript in 3–6 sentences; preserve facts and names. Language: {{USER_LOCALE}}.
""",
    "knowledge_bot/config/prompts/asr_skip_vision_gate.example.txt": """\
Decide if vision step can be skipped given ASR text quality. JSON: {"skip": bool, "reason"}.
""",
    "knowledge_bot/config/prompts/vision.example.txt": """\
Describe the scene for note enrichment; objective, no invented text on screen.
""",
    "knowledge_bot/config/prompts/ocr_clean.example.txt": """\
Clean OCR noise; keep meaningful text only. Output plain text.
""",
    "knowledge_bot/config/prompts/field_fill.example.txt": """\
Fill structured fields (category, city, steps, etc.) from note body. JSON per field schema.
""",
    "knowledge_bot/config/prompts/yt_transcript_summary.example.txt": """\
Summarize YouTube transcript; key points and quotes if present. Language: {{USER_LOCALE}}.
""",
    "knowledge_bot/config/prompts/wikilinks_select.example.txt": """\
Choose wikilinks to add from candidates relevant to note content. JSON: {"links": [...]}.
""",
    "knowledge_bot/config/prompts/serendipity_pick.example.txt": """\
Pick one note for serendipity resurfacing; explain why in one sentence.
""",
    "knowledge_bot/config/prompts/tag_ontology_propose.example.txt": """\
Propose tag merges/synonyms from singleton tags; output mapping JSON only.
""",
    "knowledge_bot/config/prompts/refill_singleton_tags.example.txt": """\
Suggest established tags to add without removing existing tags. JSON: {"add": [...]}.
""",
}

def load_scaffold_body(repo_root: Path, rel_example: str) -> str | None:
    """Prod scaffolds: prefer checked-in *.example.txt; optional SCAFFOLDS fallback."""
    path = repo_root / rel_example
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return SCAFFOLDS.get(rel_example)


DEFAULT_SLOTS = {
    "USER_LOCALE": "en",
    "USER_TONE": "concise, friendly",
    "USER_CURRENCY": "USD",
    "USER_ACCOUNTS": "(fill during onboarding: wallet, card names)",
    "USER_CATEGORIES": "(fill during onboarding)",
    "USER_PLAN_EXAMPLES": "need 500 for repairs by March",
    "USER_TASK_EXAMPLES": "Buy milk, high priority",
    "USER_GOALS": "(fill during onboarding)",
    "USER_VAULT_FOLDERS": "(fill during onboarding: Video, Knowledge, Links, …)",
    "AUTHOR_CONTEXT": "(from user_profile.md)",
}
