"""Эвристика cross-domain запросов для unified agent loop (без сценарных веток)."""
from __future__ import annotations

# Наборы пересекаются намеренно с domain_hints; цель — поймать «расходы + шаги», не «задачи + календарь».
_FINANCE = frozenset(
    "расход расходы транзакц баланс руб ₽ потрат траты доход finance badge брокер".split()
)
_HEALTH = frozenset(
    "шаг шаги сон health watch пульс вес hrv калори активност apple".split()
)
_KNOWLEDGE = frozenset("заметк база знан kb knowledge vault obsidian".split())


def cross_domain_score(text: str) -> int:
    """Сколько «семейств» доменов упомянуто в тексте (0–3)."""
    t = (text or "").lower()
    if not t.strip():
        return 0
    hits = 0
    for words in (_FINANCE, _HEALTH, _KNOWLEDGE):
        if any(w in t for w in words):
            hits += 1
    return hits


def needs_unified_agent(text: str) -> bool:
    """True → answer_unified (finance + planning + knowledge tools)."""
    return cross_domain_score(text) >= 2
