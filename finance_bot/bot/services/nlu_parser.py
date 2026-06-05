from typing import Optional, Dict, List
import logging
import json
from datetime import datetime
import calendar

from ..llm import LLMClient
from ..config_loader import get_nlu_prompt, get_nlu_config
from ..config import get_settings
from ..db import AsyncSessionLocal
from ..models import User, Account
from sqlalchemy import select
from shared.domain_messages import dmsg

log = logging.getLogger("finance.nlu")

NLU_BATCH_CHUNK_LINES = 10


def _split_transaction_batches(text: str, chunk_lines: int = NLU_BATCH_CHUNK_LINES) -> List[str]:
    """Split multiline input into line-based chunks (one LLM request per chunk)."""
    stripped = (text or "").strip()
    if not stripped:
        return []
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return [stripped]
    batches: List[str] = []
    for i in range(0, len(lines), chunk_lines):
        batches.append("\n".join(lines[i : i + chunk_lines]))
    return batches


class TransactionNLUParser:
    """Parse natural language into structured transactions."""

    def __init__(self):
        self.llm = LLMClient()
        self.base_prompt = get_nlu_prompt()
        if not self.base_prompt:
            log.warning("NLU prompt not loaded, using empty prompt")
            self.base_prompt = ""

    async def _get_user_context(self, telegram_id: int) -> str:
        """Build user-specific NLU context (accounts, categories)."""
        from ..services.categories import load_categories

        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == telegram_id))
            ).scalar_one_or_none()
            if not user:
                return ""

            accounts = (
                await session.execute(select(Account).where(Account.user_id == user.id))
            ).scalars().all()

            account_names = [acc.name for acc in accounts if acc.name]
            try:
                from bot.config_loader import is_badge_enabled
                from bot.services.badge_tracker import BadgeTracker

                if is_badge_enabled():
                    badge_name = BadgeTracker().account_name
                    if badge_name and badge_name not in account_names:
                        account_names.append(badge_name)
            except Exception:
                pass

            expense_categories = load_categories("expense")
            income_categories = load_categories("income")

            context_parts = []

            if account_names:
                accounts_list = "\n".join([f"- {name}" for name in account_names])
                block = dmsg("finance_nlu", "accounts_block", accounts_list=accounts_list)
                if not block.strip():
                    log.error(
                        "finance_nlu.accounts_block missing in domain_messages — "
                        "NLU will not see account list (%d accounts)",
                        len(account_names),
                    )
                else:
                    context_parts.append(block)

            if expense_categories:
                expense_list = "\n".join([f"- {cat}" for cat in expense_categories])
                block = dmsg(
                    "finance_nlu", "expense_categories_block", categories_list=expense_list
                )
                if not block.strip():
                    log.error(
                        "finance_nlu.expense_categories_block missing in domain_messages — "
                        "NLU will not see expense categories (%d items)",
                        len(expense_categories),
                    )
                else:
                    context_parts.append(block)

            if income_categories:
                income_list = "\n".join([f"- {cat}" for cat in income_categories])
                block = dmsg(
                    "finance_nlu", "income_categories_block", categories_list=income_list
                )
                if not block.strip():
                    log.error(
                        "finance_nlu.income_categories_block missing in domain_messages — "
                        "NLU will not see income categories (%d items)",
                        len(income_categories),
                    )
                else:
                    context_parts.append(block)

            debts_rules = dmsg("finance_nlu", "debts_rules")
            if debts_rules.strip():
                context_parts.append(debts_rules)

            return "".join(context_parts)

    def _merge_parse_responses(self, responses: List[Dict]) -> List[Dict]:
        """Merge transactions from multiple LLM responses."""
        merged: List[Dict] = []
        for resp in responses:
            if not isinstance(resp, dict):
                continue
            txns = resp.get("transactions")
            if txns:
                merged.extend(txns)
            elif "type" in resp:
                merged.append(resp)
        return merged

    async def _build_messages(
        self, text: str, telegram_id: Optional[int], batch_hint: str = ""
    ) -> List[Dict]:
        user_context = ""
        if telegram_id:
            user_context = await self._get_user_context(telegram_id)

        full_prompt = self.base_prompt
        if user_context:
            full_prompt = f"{user_context}{full_prompt}"

        try:
            import pytz

            tz = pytz.timezone(get_settings().TIMEZONE)
            now = datetime.now(tz)
            weekday = calendar.day_name[now.weekday()]
            date_ctx = dmsg("finance_nlu", "date_today", date=now.strftime("%Y-%m-%d"), weekday=weekday)
        except Exception:
            date_ctx = dmsg("finance_nlu", "date_today", date=datetime.now().strftime("%Y-%m-%d"), weekday="")

        hint = f"{batch_hint}\n" if batch_hint else ""
        user_content = date_ctx + hint + text
        return [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

    async def _parse_chunk(
        self,
        text: str,
        telegram_id: Optional[int] = None,
        batch_hint: str = "",
    ) -> List[Dict]:
        messages = await self._build_messages(text, telegram_id, batch_hint)

        log.info("NLU chunk (%d chars): %s...", len(text), text[:120].replace("\n", " | "))

        response = await self.llm.chat_json(messages=messages)

        log.debug("NLU LLM response: %s", response)

        transactions = response.get("transactions", [])
        if not transactions:
            if isinstance(response, dict) and "type" in response:
                transactions = [response]
                log.info("Single transaction at response root: %s", transactions[0])
            else:
                raise ValueError(dmsg("finance_nlu", "empty_llm_txns", response=response))

        if not isinstance(transactions, list):
            raise ValueError(dmsg("finance_nlu", "not_list_txns", type_name=type(transactions)))

        return transactions

    async def parse(self, text: str, telegram_id: Optional[int] = None) -> List[Dict]:
        """Parse text into structured transactions (may be multiple)."""
        try:
            batches = _split_transaction_batches(text)
            if len(batches) > 1:
                log.info(
                    "NLU batch: %d chunks, %d non-empty lines",
                    len(batches),
                    len([ln for ln in text.splitlines() if ln.strip()]),
                )

            all_transactions: List[Dict] = []
            for idx, chunk in enumerate(batches):
                hint = ""
                if len(batches) > 1:
                    hint = dmsg("finance_nlu", "batch_hint", index=idx + 1, total=len(batches))
                chunk_txns = await self._parse_chunk(
                    chunk, telegram_id=telegram_id, batch_hint=hint
                )
                all_transactions.extend(chunk_txns)

            log.info("NLU parsed %d transactions", len(all_transactions))
            for i, txn in enumerate(all_transactions):
                log.info(
                    "  txn %d: type=%s amount=%s category=%s account=%s",
                    i + 1,
                    txn.get("type"),
                    txn.get("amount"),
                    txn.get("category"),
                    txn.get("account"),
                )
            return all_transactions
        except Exception as e:
            log.error("NLU parse failed: %s", e, exc_info=True)
            raise
