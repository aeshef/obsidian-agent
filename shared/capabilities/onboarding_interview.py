"""Structured onboarding interview — question catalog for Cursor /setup chat."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    get_capabilities,
)

InterviewPhase = Literal[
    "intro",
    "before_layout",
    "after_layout",
    "after_secrets",
    "finalize",
]
AnswerKind = Literal["text", "comma_list", "accounts", "account_balances", "choice"]


@dataclass(frozen=True)
class InterviewQuestion:
    id: str
    phase: InterviewPhase
    modules: tuple[str, ...]  # empty = always (core)
    kind: AnswerKind
    prompt_en: str
    prompt_ru: str
    slot_keys: tuple[str, ...] = ()
    choices_en: tuple[str, ...] = ()
    choices_ru: tuple[str, ...] = ()


CORE: tuple[str, ...] = ()

QUESTIONS: tuple[InterviewQuestion, ...] = (
    InterviewQuestion(
        id="user_about",
        phase="intro",
        modules=CORE,
        kind="text",
        prompt_en="In 2–4 sentences: who you are, what you use this assistant for, anything agents should always remember.",
        prompt_ru="2–4 предложения: кто вы, зачем вам ассистент, что важно помнить всегда.",
        slot_keys=("AUTHOR_CONTEXT",),
    ),
    InterviewQuestion(
        id="user_tone",
        phase="intro",
        modules=CORE,
        kind="choice",
        prompt_en="How should the bot talk to you?",
        prompt_ru="Как боту с вами общаться?",
        slot_keys=("USER_TONE",),
        choices_en=("Short and direct", "Friendly, conversational", "Detailed and formal"),
        choices_ru=("Коротко и по делу", "Дружелюбно", "Подробно и формально"),
    ),
    InterviewQuestion(
        id="finance_currency",
        phase="intro",
        modules=(MODULE_FINANCE,),
        kind="choice",
        prompt_en="Main accounting currency?",
        prompt_ru="Основная валюта учёта?",
        slot_keys=("USER_CURRENCY",),
        choices_en=("RUB", "USD", "EUR"),
        choices_ru=("RUB (₽)", "USD ($)", "EUR (€)"),
    ),
    InterviewQuestion(
        id="finance_accounts",
        phase="intro",
        modules=(MODULE_FINANCE,),
        kind="accounts",
        prompt_en=(
            "List your accounts/cards/wallets — one per line or comma-separated. "
            "Example: Tinkoff card, Sber card, Cash"
        ),
        prompt_ru=(
            "Перечислите счета/карты/кошельки — по одному в строке или через запятую. "
            "Пример: Тинькофф, Сбер, Наличные"
        ),
        slot_keys=("USER_ACCOUNTS",),
    ),
    InterviewQuestion(
        id="finance_opening_balances",
        phase="after_secrets",
        modules=(MODULE_FINANCE,),
        kind="account_balances",
        prompt_en=(
            "Opening balance for each account (today). Format per line: "
            "Account name: amount (e.g. Tinkoff card: 45000). Use 0 if unknown."
        ),
        prompt_ru=(
            "Стартовый баланс по каждому счёту на сегодня. Формат строки: "
            "Название: сумма (например Тинькофф: 45000). 0 — если не знаете."
        ),
    ),
    InterviewQuestion(
        id="finance_categories",
        phase="intro",
        modules=(MODULE_FINANCE,),
        kind="comma_list",
        prompt_en="Top expense categories you care about (comma-separated). Defaults exist — skip to keep MVP list.",
        prompt_ru="Важные категории расходов через запятую. Можно пропустить — останется MVP-список.",
        slot_keys=("USER_CATEGORIES",),
    ),
    InterviewQuestion(
        id="planning_task_examples",
        phase="intro",
        modules=(MODULE_PLANNING,),
        kind="text",
        prompt_en="2–3 example tasks you often write (how you phrase them).",
        prompt_ru="2–3 примера задач, как вы их обычно формулируете.",
        slot_keys=("USER_TASK_EXAMPLES",),
    ),
    InterviewQuestion(
        id="planning_goals",
        phase="intro",
        modules=(MODULE_PLANNING,),
        kind="text",
        prompt_en="Current goals or quarterly focus (one line each).",
        prompt_ru="Текущие цели или фокус квартала (по одной строке).",
        slot_keys=("USER_GOALS",),
    ),
    InterviewQuestion(
        id="knowledge_folders",
        phase="intro",
        modules=(MODULE_KNOWLEDGE,),
        kind="comma_list",
        prompt_en="Main note types/folders in your vault (Video, Articles, Links, …).",
        prompt_ru="Основные типы заметок/папки (Видео, Статьи, Ссылки, …).",
        slot_keys=("USER_VAULT_FOLDERS",),
    ),
    InterviewQuestion(
        id="telegram_user_id",
        phase="after_secrets",
        modules=(MODULE_FINANCE, MODULE_KNOWLEDGE),
        kind="text",
        prompt_en="Your numeric Telegram user id (@userinfobot → /start, or bot logs after /start).",
        prompt_ru="Числовой Telegram ID (@userinfobot → /start или логи бота после /start).",
    ),
    InterviewQuestion(
        id="openrouter_api",
        phase="after_secrets",
        modules=(MODULE_KNOWLEDGE,),
        kind="text",
        prompt_en="OpenRouter API key (openrouter.ai) for vision/KB ingest — paste the key.",
        prompt_ru="Ключ OpenRouter (openrouter.ai) для vision/ингеста в KB — вставьте ключ.",
    ),
    InterviewQuestion(
        id="deploy_target",
        phase="finalize",
        modules=CORE,
        kind="choice",
        prompt_en=(
            "Where should the bot run 24/7? "
            "A small VPS is recommended so Telegram works when your laptop is off."
        ),
        prompt_ru=(
            "Где бот должен работать круглосуточно? "
            "Рекомендуем VPS — иначе бот доступен только пока включён ваш компьютер."
        ),
        choices_en=(
            "VPS (recommended) — deploy now with guided steps",
            "VPS — I'll deploy later (give me the checklist)",
            "This computer only (./scripts/run_unified_bot.sh while Mac/PC is on)",
        ),
        choices_ru=(
            "VPS (рекомендуется) — развернуть сейчас по шагам",
            "VPS — разверну позже (нужен чеклист)",
            "Только этот компьютер (./scripts/run_unified_bot.sh пока Mac/PC включён)",
        ),
    ),
    InterviewQuestion(
        id="deploy_local_ack",
        phase="finalize",
        modules=CORE,
        kind="choice",
        prompt_en="Local-only: the bot stops when this computer sleeps. Continue?",
        prompt_ru="Локально: бот останавливается, когда компьютер спит. Продолжаем?",
        choices_en=("Understood — local run is OK for now",),
        choices_ru=("Понятно — пока устраивает локальный запуск",),
    ),
    InterviewQuestion(
        id="deploy_ssh_host",
        phase="finalize",
        modules=CORE,
        kind="text",
        prompt_en=(
            "SSH target for your VPS: user@hostname or SSH config alias "
            "(e.g. root@203.0.113.10). Use SSH keys — do not send passwords here."
        ),
        prompt_ru=(
            "SSH для VPS: user@hostname или alias из ~/.ssh/config "
            "(например root@203.0.113.10). Только ключи — пароли сюда не присылайте."
        ),
    ),
    InterviewQuestion(
        id="deploy_ssh_key_ready",
        phase="finalize",
        modules=CORE,
        kind="choice",
        prompt_en="Can you already SSH to the server without a password?",
        prompt_ru="Уже можете зайти на сервер по SSH без пароля?",
        choices_en=(
            "Yes — ssh user@host works with my key",
            "No — I need SSH key setup steps",
        ),
        choices_ru=(
            "Да — ssh user@host работает с моим ключом",
            "Нет — нужна инструкция по SSH-ключу",
        ),
    ),
    InterviewQuestion(
        id="deploy_vps_later_ack",
        phase="finalize",
        modules=CORE,
        kind="choice",
        prompt_en="Saved the VPS checklist in docs/DEPLOY_VPS.md?",
        prompt_ru="Чеклист в docs/DEPLOY_VPS.md сохранён?",
        choices_en=("Yes — I'll deploy later",),
        choices_ru=("Да — разверну позже",),
    ),
    InterviewQuestion(
        id="deploy_vps_ack",
        phase="finalize",
        modules=CORE,
        kind="choice",
        prompt_en="After ./scripts/deploy.sh --prod — did the bot start on the VPS?",
        prompt_ru="После ./scripts/deploy.sh --prod — бот запустился на VPS?",
        choices_en=(
            "Yes — unified_bot is UP on the server",
            "Not yet — I'll finish deploy using docs/DEPLOY_VPS.md",
        ),
        choices_ru=(
            "Да — unified_bot на сервере работает",
            "Ещё нет — доделаю по docs/DEPLOY_VPS.md",
        ),
    ),
)


def _module_active(q: InterviewQuestion, prof: CapabilityProfile) -> bool:
    if not q.modules:
        return True
    return any(prof.module(m) for m in q.modules)


def questions_for_profile(
    profile: Optional[CapabilityProfile] = None,
    *,
    phase: Optional[InterviewPhase] = None,
    locale: str = "en",
) -> list[InterviewQuestion]:
    prof = profile or get_capabilities()
    loc = (locale or "en").strip().lower()
    out: list[InterviewQuestion] = []
    for q in QUESTIONS:
        if not _module_active(q, prof):
            continue
        if phase is not None and q.phase != phase:
            continue
        out.append(q)
    return out


def prompt_for(q: InterviewQuestion, locale: str) -> str:
    loc = (locale or "en").strip().lower()
    return q.prompt_ru if loc.startswith("ru") else q.prompt_en


def choices_for(q: InterviewQuestion, locale: str) -> tuple[str, ...]:
    loc = (locale or "en").strip().lower()
    return q.choices_ru if loc.startswith("ru") else q.choices_en


def question_by_id(qid: str) -> Optional[InterviewQuestion]:
    for q in QUESTIONS:
        if q.id == qid:
            return q
    return None
