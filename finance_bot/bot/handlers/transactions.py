from decimal import Decimal
from typing import Optional, Tuple, List

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State, default_state
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

from ..db import AsyncSessionLocal
from ..models import User, Account, Transaction
from ..services.categories import load_categories
from ..services.badge_tracker import is_badge_account_name
from ..services.crypto_prices import fetch_prices_rub
from ..services.nlu_parser import TransactionNLUParser
from ..services.asr import transcribe_audio
from ..config_loader import get_nlu_config
from datetime import datetime, time
import tempfile
from pathlib import Path
import logging

log = logging.getLogger("finance.transactions")


router = Router()


def _parse_occurred_at(parsed: dict) -> datetime:
    """Дата/время операции из результата NLU: occurred_at YYYY-MM-DD или сегодня (полдень по локальному времени)."""
    raw = parsed.get("occurred_at")
    if not raw:
        return datetime.now()
    s = (raw if isinstance(raw, str) else str(raw)).strip()[:10]
    if len(s) < 10:
        return datetime.now()
    try:
        from datetime import date
        y, m, d = int(s[:4]), int(s[5:7]), int(s[8:10])
        return datetime.combine(date(y, m, d), time(12, 0, 0))
    except (ValueError, TypeError):
        return datetime.now()


class AddTxnState(StatesGroup):
    type = State()
    amount = State()
    category = State()
    account = State()
    confirm = State()
    wizard_message_id = State()


class ConfirmTransactionsState(StatesGroup):
    """Состояние для подтверждения нескольких транзакций"""
    transactions = State()  # JSON список транзакций
    current_index = State()  # Индекс текущей транзакции
    wizard_message_id = State()


def inline_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="wizard:cancel")]]
    )


async def _set_wizard_message(state: FSMContext, message: types.Message) -> None:
    await state.update_data(wizard_message_id=message.message_id)


async def _edit_wizard(message: types.Message, state: FSMContext, text: str, kb: Optional[InlineKeyboardMarkup] = None) -> None:
    data = await state.get_data()
    msg_id = data.get("wizard_message_id")
    if msg_id:
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=text, reply_markup=kb)
            return
        except Exception as e:
            # Если не удалось отредактировать, отправляем новое сообщение
            log.warning(f"Не удалось отредактировать wizard сообщение {msg_id}: {e}")
    m = await message.answer(text, reply_markup=kb)
    await _set_wizard_message(state, m)


def _categories_keyboard(kind: str) -> InlineKeyboardMarkup:
    cats = load_categories(kind)
    rows = []
    row: List[InlineKeyboardButton] = []
    for c in cats:
        row.append(InlineKeyboardButton(text=c, callback_data=f"wizard:cat:{c}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="📝 Ввести текстом", callback_data="wizard:cat_text")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="action:menu"), InlineKeyboardButton(text="❌ Отмена", callback_data="wizard:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _main_menu_inline() -> InlineKeyboardMarkup:
    """Возвращает кнопку меню (используется из start.py)"""
    from .start import main_menu_inline
    return main_menu_inline()


@router.callback_query(F.data == "action:add_expense")
async def add_expense_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await state.set_state(AddTxnState.type)
    await state.update_data(type="expense")
    await state.set_state(AddTxnState.amount)
    await _edit_wizard(message, state, "Введите сумму расхода (например: 500.00):", inline_cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "action:add_income")
async def add_income_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await state.set_state(AddTxnState.type)
    await state.update_data(type="income")
    await state.set_state(AddTxnState.amount)
    await _edit_wizard(message, state, "Введите сумму дохода (например: 1500.00):", inline_cancel_kb())
    await callback.answer()


# УДАЛЕНО: обработка голосовых в wizard (AddTxnState.amount, F.voice)
# Голосовые обрабатываются только в основном handler @router.message(F.voice)


@router.message(AddTxnState.amount, F.text)
async def add_amount(message: types.Message, state: FSMContext) -> None:
    """ВСЕ текстовые сообщения в wizard обрабатываем через LLM - никаких проверок"""
    text = message.text.strip()
    log.info(f"📝 Текст '{text}' получен в wizard - ОЧИЩАЕМ и обрабатываем через LLM")
    await state.clear()
    await _process_transactions(text, message, state)


@router.callback_query(AddTxnState.category, F.data.startswith("wizard:cat:"))
async def choose_category_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    cat = callback.data.split(":", 2)[-1]
    await state.update_data(category=cat)

    # offer accounts to choose
    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        accounts = [a for a in accounts if not a.is_external_balance]
        if not accounts:
            acc = Account(user_id=user.id, name="Кошелек", type="wallet", currency=user.base_currency)
            session.add(acc)
            await session.commit()
            accounts = [acc]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=a.name, callback_data=f"wizard:acc:{a.id}")]
            for a in accounts
        ]
        + [[InlineKeyboardButton(text="❌ Отмена", callback_data="wizard:cancel")]]
    )
    await state.set_state(AddTxnState.account)
    await _edit_wizard(message, state, "Выберите счет:", kb)
    await callback.answer()


@router.callback_query(AddTxnState.category, F.data == "wizard:cat_text")
async def choose_category_text_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    await _edit_wizard(message, state, "Введите категорию текстом:", inline_cancel_kb())
    await callback.answer()


# УДАЛЕНО: @router.message(AddTxnState.category, F.voice)
# Голосовые больше не обрабатываются в wizard - только основной handler


@router.message(AddTxnState.category, F.text)
async def add_category(message: types.Message, state: FSMContext) -> None:
    await state.update_data(category=message.text.strip())
    # delete user message with raw category text
    try:
        await message.delete()
    except Exception as e:
        log.debug(f"Не удалось удалить сообщение пользователя: {e}")

    # offer accounts to choose
    async with AsyncSessionLocal() as session:
        tg_id = message.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        accounts = [a for a in accounts if not a.is_external_balance]
        if not accounts:
            acc = Account(user_id=user.id, name="Кошелек", type="wallet", currency=user.base_currency)
            session.add(acc)
            await session.commit()
            accounts = [acc]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=a.name, callback_data=f"wizard:acc:{a.id}")]
            for a in accounts
        ]
        + [[InlineKeyboardButton(text="❌ Отмена", callback_data="wizard:cancel")]]
    )
    await state.set_state(AddTxnState.account)
    await _edit_wizard(message, state, "Выберите счет:", kb)


@router.callback_query(AddTxnState.account, F.data.startswith("wizard:acc:"))
async def add_account_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обрабатывает выбор счета и показывает подтверждение"""
    message = callback.message
    acc_id_str = callback.data.split(":")[-1]
    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        account = (
            await session.execute(select(Account).where(Account.user_id == user.id, Account.id == int(acc_id_str)))
        ).scalar_one_or_none()
        if account is None or account.is_external_balance:
            await callback.answer("Нельзя выбрать этот счет", show_alert=True)
            return
        
        # Сохраняем ID счета для подтверждения
        await state.update_data(account_id=account.id)
        
        # Показываем превью транзакции для подтверждения
        data = await state.get_data()
        amount = Decimal(data["amount"])
        txn_type = data["type"]
        category = data.get("category", "Без категории")
        
        emoji = "➖" if txn_type == "expense" else "➕"
        text = f"{emoji} <b>Подтвердите транзакцию:</b>\n\n"
        text += f"Тип: {txn_type}\n"
        text += f"Сумма: {amount:,.2f} {account.currency}\n"
        text += f"Категория: {category}\n"
        text += f"Счет: {account.name}"
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data="wizard:confirm")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="wizard:cancel")],
            ]
        )
        
        await state.set_state(AddTxnState.confirm)
        await _edit_wizard(message, state, text, kb)
        await callback.answer()


@router.callback_query(AddTxnState.confirm, F.data == "wizard:confirm")
async def confirm_transaction_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Записывает транзакцию в БД после подтверждения"""
    message = callback.message
    async with AsyncSessionLocal() as session:
        tg_id = callback.from_user.id
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
        
        data = await state.get_data()
        account_id = data.get("account_id")
        if not account_id:
            await callback.answer("Ошибка: счет не выбран", show_alert=True)
            await state.clear()
            return
        
        account = (
            await session.execute(select(Account).where(Account.user_id == user.id, Account.id == account_id))
        ).scalar_one_or_none()
        
        if not account:
            await callback.answer("Ошибка: счет не найден", show_alert=True)
            await state.clear()
            return

        txn = Transaction(
            user_id=user.id,
            account_id=account.id,
            type=data["type"],
            amount=Decimal(data["amount"]),
            currency=account.currency,
            category=data.get("category"),
        )
        session.add(txn)
        await session.commit()

    await state.clear()
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text="✅ Транзакция записана",
        reply_markup=_main_menu_inline(),
    )
    await callback.answer()


@router.callback_query(F.data == "wizard:cancel")
async def wizard_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()


async def _render_balance(tg_id: int) -> Tuple[str, types.InlineKeyboardMarkup]:
    """Формирует текст баланса и клавиатуру"""
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            return "Сначала нажмите /start", None
        
        accounts = (await session.execute(select(Account).where(Account.user_id == user.id))).scalars().all()

        # compute balances per account
        async def acc_balance(acc: Account) -> Decimal:
            inc = (
                await session.execute(
                    select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                        Transaction.account_id == acc.id, Transaction.type == "income"
                    )
                )
            ).scalar_one()
            exp = (
                await session.execute(
                    select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                        Transaction.account_id == acc.id, Transaction.type == "expense"
                    )
                )
            ).scalar_one()
            from_txn = Decimal(inc) - Decimal(exp)
            # Брокер: баланс только из API (external_balance)
            if acc.is_external_balance and acc.external_balance is not None:
                return Decimal(acc.external_balance)
            # Карты/кошельки: external_balance из init_accounts как база + транзакции
            base = Decimal(acc.external_balance) if acc.external_balance is not None else Decimal(0)
            return base + from_txn

        groups = {
            "cards": [],
            "invest": [],
            "crypto": [],
            "debts": [],
            "cash": [],
        }
        # Pre-fetch crypto prices
        crypto_symbols: set[str] = set()
        for a in accounts:
            if a.type == "crypto":
                crypto_symbols.add(a.currency.upper())
        prices_rub = {}
        if crypto_symbols:
            prices_rub = await fetch_prices_rub(sorted(list(crypto_symbols)))

        for acc in accounts:
            if is_badge_account_name(acc.name):
                continue
            bal = await acc_balance(acc)
            entry = (acc, bal)
            if acc.type in ("card",) or (acc.type == "wallet" and "нал" not in acc.name.lower()):
                if bal != 0:
                    groups["cards"].append(entry)
            elif acc.type == "wallet":
                if bal != 0:
                    groups["cash"].append(entry)
            elif acc.type.startswith("broker"):
                if bal != 0:
                    groups["invest"].append(entry)
            elif acc.type == "crypto":
                # show crypto even if zero
                groups["crypto"].append(entry)
            elif acc.type in ("receivable", "liability_payable"):
                if bal != 0:
                    groups["debts"].append(entry)
            else:
                if bal != 0:
                    groups["cards"].append(entry)

        def fmt_line(acc: Account, amount: Decimal) -> str:
            label_raw = acc.name
            if acc.type == "receivable":
                label_raw = f"{acc.name.split(':',1)[-1]} (мне должны)"
            elif acc.type == "liability_payable":
                label_raw = f"{acc.name.split(':',1)[-1]} (я должен)"
            label = label_raw[:24]
            if acc.type == "crypto":
                sym = acc.currency.upper()
                amt_crypto = f"{amount:.8f} {sym}"
                rub_val = None
                if sym in prices_rub:
                    rub_val = float(amount) * float(prices_rub[sym])
                rub_str = f" (~{rub_val:.2f} RUB)" if rub_val is not None else ""
                return f"{label:<24} {amt_crypto}{rub_str}"
            amt = f"{amount:.2f}" if acc.currency in ("RUB", "RUR", "USD", "EUR", "GBP", "CNY") else f"{amount:.6f}"
            return f"{label:<24} {amt:>14} {acc.currency}"

        sections: List[str] = []
        def add_section(title: str, items: List[Tuple[Account, Decimal]]):
            if not items:
                return
            sections.append(title)
            for acc, bal in items:
                sections.append(fmt_line(acc, bal))
            sections.append("")

        sections.append("📊 Баланс")
        sections.append("<pre>")
        add_section("💳 Карты", groups["cards"])
        add_section("💵 Наличные", groups["cash"])
        add_section("📈 Инвестиции", groups["invest"])
        add_section("🪙 Крипто", groups["crypto"])
        add_section("🏦 Долги", groups["debts"])
        
        # Если только "📊 Баланс" и "<pre>" - значит нет счетов или все балансы нулевые
        if len(sections) == 2:
            # Проверяем, есть ли вообще счета (даже с нулевым балансом)
            has_any_accounts = len(accounts) > 0
            if has_any_accounts:
                sections.append("Все балансы равны нулю")
            else:
                sections.append("Нет активных счетов")
                sections.append("")
                sections.append("Добавьте счет через:")
                sections.append("🔄 Синхронизация → 💳 Добавить карту/счет")
        
        if sections and sections[-1] == "":
            sections.pop()
        sections.append("</pre>")

        text = "\n".join(sections)
        log.info(f"📊 Баланс сформирован для пользователя {tg_id}: {len(groups['cards'])} карт, {len(groups['invest'])} инвестиций")
        return text, _main_menu_inline()


@router.callback_query(F.data == "action:balance")
async def show_balance_cb(callback: types.CallbackQuery) -> None:
    """Показывает баланс для callback query (inline кнопка)"""
    try:
        log.info(f"📊 Запрос баланса от пользователя {callback.from_user.id}")
        text, kb = await _render_balance(callback.from_user.id)
        log.info(f"📊 Текст баланса сформирован, длина: {len(text)} символов")
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            log.info(f"✅ Баланс успешно отредактирован")
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                # Сообщение уже актуально — не дублируем
                pass
            else:
                log.error(f"❌ Ошибка при редактировании: {e}")
                await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            log.error(f"❌ Ошибка при редактировании сообщения: {e}", exc_info=True)
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        log.error(f"❌ Ошибка при формировании баланса: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    await callback.answer()


def _looks_like_transaction(text: str) -> bool:
    """Проверяет, похоже ли сообщение на финансовую транзакцию"""
    nlu_cfg = get_nlu_config()
    keywords = nlu_cfg.get("transaction_keywords", [
        "потратил", "зарплата", "перевел", "долг", "должен", "должны", "вернул",
        "купил", "оплатил", "получил", "доход", "расход",
        "подписка", "заплатил", "отдал", "взял",
        "пополнил", "вывел", "брокер", "погасил", "погасили",
        "мне", "я должен", "я должна"
    ])
    min_length = nlu_cfg.get("min_text_length", 3)
    
    if len(text.strip()) < min_length:
        return False
    
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


async def _get_or_create_account(session, user_id: int, account_name: Optional[str] = None) -> Account:
    """Находит или создает счет"""
    if account_name:
        # Ищем по названию (нечеткое совпадение)
        accounts = (
            await session.execute(select(Account).where(Account.user_id == user_id))
        ).scalars().all()
        
        # Нормализуем название для поиска (убираем пробелы, приводим к нижнему регистру)
        account_name_normalized = account_name.lower().strip().replace(" ", "")
        
        # Сначала ищем точное совпадение (регистронезависимое)
        for acc in accounts:
            if acc.name.lower().strip() == account_name.lower().strip():
                return acc
        
        # Затем нечеткий матчинг по ключевым словам
        for acc in accounts:
            acc_name_normalized = acc.name.lower().strip().replace(" ", "")
            # Проверяем вхождение в обе стороны
            if account_name_normalized in acc_name_normalized or acc_name_normalized in account_name_normalized:
                return acc
            # Также проверяем по словам (если одно название содержит все слова другого)
            account_words = set(account_name_normalized.split())
            acc_words = set(acc_name_normalized.split())
            if account_words and acc_words and (account_words.issubset(acc_words) or acc_words.issubset(account_words)):
                return acc
    
    # Если не нашли, берем первый счет или создаем дефолтный
    account = (
        await session.execute(select(Account).where(Account.user_id == user_id).limit(1))
    ).scalar_one_or_none()
    
    if not account:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        account = Account(
            user_id=user_id,
            name="Кошелек",
            type="wallet",
            currency=user.base_currency
        )
        session.add(account)
        await session.flush()
    
    return account


async def _handle_broker_withdraw(session, user: User, parsed: dict, message: types.Message):
    """Обрабатывает вывод с брокера (как в investments.py)"""
    nlu_cfg = get_nlu_config()
    broker_cats = nlu_cfg.get("broker_categories", {})
    
    to_account = await _get_or_create_account(session, user.id, parsed.get("to_account"))
    amount = Decimal(str(parsed["amount"]))
    fee = Decimal(str(parsed.get("fee", 0)))
    
    withdraw_category = broker_cats.get("withdraw", "Вывод с брокера")
    fee_category = broker_cats.get("fee", "Комиссия брокера")
    
    occurred = _parse_occurred_at(parsed)
    # Доход на карту
    session.add(Transaction(
        user_id=user.id,
        account_id=to_account.id,
        type="income",
        amount=amount,
        currency=to_account.currency,
        category=withdraw_category,
        description=withdraw_category,
        occurred_at=occurred,
    ))
    
    # Комиссия (если есть)
    if fee > 0:
        session.add(Transaction(
            user_id=user.id,
            account_id=to_account.id,
            type="expense",
            amount=fee,
            currency=to_account.currency,
            category=fee_category,
            description=fee_category,
            occurred_at=occurred,
        ))
    
    await session.flush()
    # Не делаем commit здесь - он будет в _process_transactions


def _format_transaction_response(parsed: dict, account: Account) -> str:
    """Форматирует ответ пользователю"""
    type_emoji = {
        "expense": "➖",
        "income": "➕",
        "transfer": "↔️",
        "debt_receivable": "💸",
        "debt_payable": "💸",
        "debt_settle_receivable": "💸"
    }
    emoji = type_emoji.get(parsed.get("type", ""), "💰")
    
    lines = [f"{emoji} Записал:"]
    lines.append(f"- Сумма: {parsed['amount']:,.0f} {parsed.get('currency', 'RUB')}")
    lines.append(f"- Тип: {parsed['type']}")
    if parsed.get("category"):
        lines.append(f"- Категория: {parsed['category']}")
    lines.append(f"- Счет: {account.name}")
    if parsed.get("description"):
        lines.append(f"- Описание: {parsed['description']}")
    
    return "\n".join(lines)


async def _get_missing_fields(parsed: dict, tg_id: int) -> dict:
    """Определяет, какие поля не распознаны и требуют выбора"""
    missing = {}
    
    log.debug(f"🔍 Проверка полей для транзакции: {parsed}")
    
    # Проверяем обязательные поля для обычных транзакций
    if parsed.get("type") in ["expense", "income"]:
        if not parsed.get("amount"):
            missing["amount"] = True
            log.warning(f"  ❌ amount отсутствует")
        else:
            log.info(f"  ✅ amount = {parsed.get('amount')}")
        
        # Проверяем не только наличие, но и существование категории
        category_name = parsed.get("category")
        if not category_name:
            missing["category"] = True
            log.warning(f"  ❌ category отсутствует")
        else:
            # Проверяем, существует ли такая категория в конфиге
            from ..services.categories import load_categories
            kind = "expense" if parsed.get("type") == "expense" else "income"
            available_categories = load_categories(kind)
            
            # Ищем категорию (нечеткое совпадение)
            category_found = False
            found_category_name = None
            category_name_lower = category_name.lower()
            for cat in available_categories:
                if category_name_lower == cat.lower() or category_name_lower in cat.lower() or cat.lower() in category_name_lower:
                    category_found = True
                    found_category_name = cat
                    # Сохраняем найденное название категории для отображения
                    parsed["_found_category_name"] = cat
                    log.info(f"  ✅ category = {category_name} (найдена: {cat})")
                    break
            
            if not category_found:
                missing["category"] = True
                log.warning(f"  ❌ category '{category_name}' не найдена среди доступных категорий {kind}")
        
        # Проверяем не только наличие, но и существование счета
        account_name = parsed.get("account")
        if not account_name:
            missing["account"] = True
            log.warning(f"  ❌ account отсутствует")
        else:
            # Проверяем, существует ли такой счет у пользователя
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
                if not user:
                    missing["account"] = True
                    log.warning(f"  ❌ пользователь не найден")
                else:
                    accounts = (
                        await session.execute(select(Account).where(Account.user_id == user.id))
                    ).scalars().all()
                    
                    # Ищем счет по названию (нечеткое совпадение)
                    account_found = False
                    found_account_name = None
                    account_name_lower = account_name.lower()
                    for acc in accounts:
                        if account_name_lower in acc.name.lower() or acc.name.lower() in account_name_lower:
                            account_found = True
                            found_account_name = acc.name
                            # Сохраняем найденное название счета в parsed для отображения
                            parsed["_found_account_name"] = acc.name
                            log.info(f"  ✅ account = {parsed.get('account')} (найден: {acc.name})")
                            break
                    
                    if not account_found:
                        missing["account"] = True
                        log.warning(f"  ❌ account '{account_name}' не найден среди существующих счетов")
    
    # Для переводов
    elif parsed.get("type") == "transfer":
        if not parsed.get("amount"):
            missing["amount"] = True
        if not parsed.get("from_account"):
            missing["from_account"] = True
        if not parsed.get("to_account"):
            missing["to_account"] = True
    
    # Для выводов с брокера
    elif parsed.get("type") == "broker_withdraw":
        if not parsed.get("amount"):
            missing["amount"] = True
        if not parsed.get("to_account"):
            missing["to_account"] = True
        # Проверяем счет получателя
        to_account_name = parsed.get("to_account")
        if to_account_name:
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
                if not user:
                    log.warning(f"  ❌ пользователь не найден для broker_withdraw")
                    missing["to_account"] = True
                else:
                    accounts = (
                        await session.execute(select(Account).where(Account.user_id == user.id))
                    ).scalars().all()
                    account_found = False
                    to_account_name_lower = to_account_name.lower()
                    for acc in accounts:
                        if to_account_name_lower in acc.name.lower() or acc.name.lower() in to_account_name_lower:
                            account_found = True
                            parsed["_found_to_account_name"] = acc.name
                            log.info(f"  ✅ to_account = {to_account_name} (найден: {acc.name})")
                            break
                    if not account_found:
                        missing["to_account"] = True
                        log.warning(f"  ❌ to_account '{to_account_name}' не найден среди существующих счетов")
    
    # Погашение долга мне (мне вернули) — нужны сумма, контрагент и счёт зачисления
    elif parsed.get("type") == "debt_settle_receivable":
        if not parsed.get("amount"):
            missing["amount"] = True
        if not parsed.get("counterparty"):
            missing["counterparty"] = True
        account_name = parsed.get("account")
        if not account_name:
            missing["account"] = True
        else:
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
                if not user:
                    missing["account"] = True
                else:
                    accounts = (
                        await session.execute(select(Account).where(Account.user_id == user.id, Account.is_external_balance == False))
                    ).scalars().all()
                    account_name_lower = account_name.lower()
                    account_found = False
                    for acc in accounts:
                        if account_name_lower in acc.name.lower() or acc.name.lower() in account_name_lower:
                            account_found = True
                            parsed["_found_account_name"] = acc.name
                            break
                    if not account_found:
                        missing["account"] = True

    # Для долгов (новый долг: мне должны / я должен)
    elif parsed.get("type") in ["debt_receivable", "debt_payable"]:
        if not parsed.get("amount"):
            missing["amount"] = True
        if not parsed.get("counterparty"):
            missing["counterparty"] = True
        # Для "мне должны" нужен счет списания, чтобы корректно уменьшать баланс карты.
        if parsed.get("type") == "debt_receivable" and not parsed.get("account"):
            missing["account"] = True
        # Для "я должен" счет необязателен.
        elif not parsed.get("account"):
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
                if not user:
                    missing["account"] = True
                    log.warning(f"  ❌ пользователь не найден")
                else:
                    accounts = (
                        await session.execute(select(Account).where(Account.user_id == user.id).limit(1))
                    ).scalars().all()
                    if not accounts:
                        missing["account"] = True
                    else:
                        default_account = accounts[0]
                        parsed["account"] = default_account.name
                        parsed["_found_account_name"] = default_account.name
                        log.info(f"  ✅ account не указан для долга, используем дефолтный: {default_account.name}")
    
    return missing


# Экспортируем для использования в transactions_confirm.py
async def show_transaction_confirmation(parsed: dict, message: types.Message, state: FSMContext, index: int, total: int, tg_id: Optional[int] = None) -> None:
    """Показывает подтверждение транзакции с кнопками для недостающих полей"""
    from ..services.categories import load_categories
    
    # Получаем tg_id из параметра или из message
    if tg_id is None:
        if hasattr(message, 'from_user') and message.from_user:
            tg_id = message.from_user.id
        elif hasattr(message, 'chat'):
            tg_id = message.chat.id
        else:
            log.error(f"Не могу определить tg_id из message типа {type(message)}")
            return
    
    log.info(f"📋 Показываем транзакцию {index + 1} из {total} для пользователя {tg_id}")
    
    missing = await _get_missing_fields(parsed, tg_id)
    
    # Формируем превью транзакции
    lines = []
    if total > 1:
        lines.append(f"📋 <b>Транзакция {index + 1} из {total}</b>\n")
    
    type_emoji = {
        "expense": "➖",
        "income": "➕",
        "transfer": "↔️",
        "debt_receivable": "💸",
        "debt_payable": "💸",
        "debt_settle_receivable": "💸",
        "broker_withdraw": "📈",
        "account_balance": "💳"
    }
    emoji = type_emoji.get(parsed.get("type", ""), "💰")
    lines.append(f"{emoji} <b>Транзакция:</b>")
    
    # Показываем распознанные поля
    if parsed.get("amount"):
        lines.append(f"💰 Сумма: {parsed['amount']:,.0f} {parsed.get('currency', 'RUB')}")
    elif missing.get("amount"):
        lines.append("💰 Сумма: ❌ не распознана")
    
    if parsed.get("type"):
        type_name = {
            "expense": "Расход",
            "income": "Доход",
            "transfer": "Перевод",
            "debt_receivable": "Мне должны",
            "debt_payable": "Я должен",
            "debt_settle_receivable": "Погашение долга (мне вернули)",
            "broker_withdraw": "Вывод с брокера",
            "account_balance": "Баланс счета"
        }.get(parsed["type"], parsed["type"])
        lines.append(f"📊 Тип: {type_name}")
    
    if parsed.get("category"):
        # Показываем найденное название категории из конфига, если оно есть
        category_display = parsed.get("_found_category_name") or parsed.get("category")
        lines.append(f"🏷 Категория: {category_display}")
    elif missing.get("category"):
        lines.append("🏷 Категория: ❌ не распознана")
    
    if parsed.get("account"):
        # Показываем найденное название счета, если оно есть (полное название из БД)
        account_display = parsed.get("_found_account_name") or parsed.get("account")
        lines.append(f"💳 Счет: {account_display}")
    elif missing.get("account"):
        lines.append("💳 Счет: ❌ не распознан")
    
    if parsed.get("from_account"):
        lines.append(f"⬅️ Откуда: {parsed['from_account']}")
    elif missing.get("from_account"):
        lines.append("⬅️ Откуда: ❌ не распознан")
    
    if parsed.get("to_account"):
        # Показываем найденное название счета, если оно есть (полное название из БД)
        to_account_display = parsed.get("_found_to_account_name") or parsed.get("to_account")
        lines.append(f"➡️ Куда: {to_account_display}")
    elif missing.get("to_account"):
        lines.append("➡️ Куда: ❌ не распознан")

    if parsed.get("type") == "broker_withdraw":
        raw_fee = parsed.get("fee")
        if raw_fee is not None:
            try:
                fee_dec = Decimal(str(raw_fee))
                if fee_dec > 0:
                    lines.append(f"🏦 Комиссия брокера: {fee_dec:,.0f} {parsed.get('currency', 'RUB')}")
                else:
                    lines.append("🏦 Комиссия брокера: нет")
            except Exception:
                lines.append(f"🏦 Комиссия брокера: {raw_fee}")
    
    if parsed.get("counterparty"):
        lines.append(f"👤 Контрагент: {parsed['counterparty']}")
    elif missing.get("counterparty"):
        lines.append("👤 Контрагент: ❌ не распознан")
    
    if parsed.get("description"):
        lines.append(f"📝 Описание: {parsed['description']}")
    
    # Дата операции (если извлекли из текста — показываем)
    occ = _parse_occurred_at(parsed)
    occ_date_str = occ.strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    if occ_date_str != today_str:
        lines.append(f"📅 Дата: {occ_date_str}")
    else:
        lines.append("📅 Дата: сегодня")
    
    text = "\n".join(lines)
    
    # Формируем клавиатуру с кнопками только для недостающих полей
    kb_rows = []
    
    if missing.get("amount"):
        kb_rows.append([InlineKeyboardButton(text="💰 Указать сумму", callback_data=f"txn:set_amount:{index}")])
    
    if missing.get("category"):
        if parsed.get("type") in ["expense", "income"]:
            kind = "expense" if parsed.get("type") == "expense" else "income"
            cats = load_categories(kind)
            # Показываем первые 6 категорий
            for i in range(0, min(6, len(cats)), 2):
                row = []
                if i < len(cats):
                    row.append(InlineKeyboardButton(text=cats[i], callback_data=f"txn:set_cat:{index}:{cats[i]}"))
                if i + 1 < len(cats):
                    row.append(InlineKeyboardButton(text=cats[i+1], callback_data=f"txn:set_cat:{index}:{cats[i+1]}"))
                if row:
                    kb_rows.append(row)
            if len(cats) > 6:
                kb_rows.append([InlineKeyboardButton(text="📝 Ввести категорию", callback_data=f"txn:set_cat_text:{index}")])
    
    if missing.get("account"):
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
            if not user:
                log.error(f"Пользователь {tg_id} не найден при отображении кнопок счетов")
                return
            accounts = (
                await session.execute(select(Account).where(Account.user_id == user.id, Account.is_external_balance == False))
            ).scalars().all()
            # Показываем первые 6 счетов
            for i in range(0, min(6, len(accounts)), 2):
                row = []
                if i < len(accounts):
                    row.append(InlineKeyboardButton(text=accounts[i].name, callback_data=f"txn:set_acc:{index}:{accounts[i].id}"))
                if i + 1 < len(accounts):
                    row.append(InlineKeyboardButton(text=accounts[i+1].name, callback_data=f"txn:set_acc:{index}:{accounts[i+1].id}"))
                if row:
                    kb_rows.append(row)
    
    if missing.get("from_account"):
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
            if user:
                accounts = (
                    await session.execute(select(Account).where(Account.user_id == user.id))
                ).scalars().all()
                for i in range(0, min(6, len(accounts)), 2):
                    row = []
                    if i < len(accounts):
                        row.append(InlineKeyboardButton(text=accounts[i].name, callback_data=f"txn:set_from:{index}:{accounts[i].id}"))
                    if i + 1 < len(accounts):
                        row.append(InlineKeyboardButton(text=accounts[i+1].name, callback_data=f"txn:set_from:{index}:{accounts[i+1].id}"))
                    if row:
                        kb_rows.append(row)
    
    if missing.get("to_account"):
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
            if user:
                accounts = (
                    await session.execute(select(Account).where(Account.user_id == user.id))
                ).scalars().all()
                for i in range(0, min(6, len(accounts)), 2):
                    row = []
                    if i < len(accounts):
                        row.append(InlineKeyboardButton(text=accounts[i].name, callback_data=f"txn:set_to:{index}:{accounts[i].id}"))
                    if i + 1 < len(accounts):
                        row.append(InlineKeyboardButton(text=accounts[i+1].name, callback_data=f"txn:set_to:{index}:{accounts[i+1].id}"))
                    if row:
                        kb_rows.append(row)
    
    if missing.get("counterparty"):
        kb_rows.append([InlineKeyboardButton(text="👤 Указать контрагента", callback_data=f"txn:set_counterparty:{index}")])
    
    # Кнопка подтверждения, если все поля заполнены
    if not missing:
        kb_rows.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"txn:confirm:{index}")])
    
    # Кнопки навигации
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"txn:prev:{index}"))
    if index < total - 1:
        nav_row.append(InlineKeyboardButton(text="➡️ Следующая", callback_data=f"txn:next:{index}"))
    if nav_row:
        kb_rows.append(nav_row)
    
    kb_rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="txn:cancel")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    # Отправляем или редактируем сообщение
    # Определяем bot и chat_id
    if hasattr(message, 'bot'):
        bot = message.bot
    else:
        log.error(f"Не могу определить bot из message типа {type(message)}")
        return
    
    chat_id = message.chat.id if hasattr(message, 'chat') else None
    if not chat_id:
        log.error(f"Не могу определить chat_id из message типа {type(message)}")
        return
    
    # Проверяем, есть ли уже сообщение для редактирования
    data = await state.get_data()
    msg_id = data.get("wizard_message_id")
    
    log.debug(f"📝 Редактирование сообщения: msg_id={msg_id}, chat_id={chat_id}, index={index}, total={total}")
    
    # Если есть сохраненное сообщение - пытаемся его отредактировать
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
            log.debug(f"✅ Сообщение {msg_id} успешно отредактировано")
            return
        except Exception as e:
            log.warning(f"⚠️ Не удалось отредактировать сообщение {msg_id}: {e}, создаем новое")
            # Если не удалось отредактировать (например, сообщение изменилось), создаем новое
    
    # Если нет сохраненного msg_id или не удалось отредактировать - отправляем новое сообщение
    log.debug(f"📤 Отправляем новое сообщение в chat_id={chat_id}")
    m = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.update_data(wizard_message_id=m.message_id)
    log.debug(f"✅ Новое сообщение {m.message_id} отправлено и сохранено в state")


async def _process_transactions(
    text: str,
    message: types.Message,
    state: FSMContext,
    badge_defaults: Optional[dict] = None,
) -> None:
    """Обрабатывает текст с транзакциями (может быть несколько) - показывает подтверждения.

    badge_defaults: если передан, применяется как fallback для полей type/account/category
    которые NLU не распознал. Используется из badge-handler'а.
    """
    log.info(f"🔍 Обработка текста: '{text}'")
    log.info(f"🔍 _process_transactions ВЫЗВАНА! User: {message.from_user.id}")
    
    parser = TransactionNLUParser()
    # Передаем telegram_id для контекста пользователя
    try:
        parsed_list = await parser.parse(text, telegram_id=message.from_user.id)
    except Exception as e:
        log.error(f"❌ Ошибка парсинга транзакции: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка при распознавании транзакции:\n\n{str(e)}\n\nТекст: {text}")
        return
    
    log.info(f"📊 Распознано транзакций: {len(parsed_list)}")
    for i, parsed in enumerate(parsed_list):
        log.info(f"  Транзакция {i+1}: {parsed}")
    
    if not parsed_list:
        # Если LLM не распознал транзакцию - показываем ошибку
        log.warning(f"❌ LLM не распознал транзакцию из текста: '{text}'")
        await message.answer(f"❌ Не удалось распознать транзакцию из текста:\n\n{text}\n\nПопробуйте переформулировать или отправьте транзакции по одной.")
        return

    # Применяем badge defaults: если NLU не заполнил поле — берём из defaults
    if badge_defaults:
        for parsed in parsed_list:
            for key, val in badge_defaults.items():
                if not parsed.get(key):
                    parsed[key] = val

    # Для каждой транзакции проверяем недостающие поля
    for i, parsed in enumerate(parsed_list):
        missing = await _get_missing_fields(parsed, message.from_user.id)
        log.info(f"🔍 Транзакция {i+1}: недостающие поля: {list(missing.keys()) if missing else 'нет'}")
        if missing:
            log.warning(f"  ⚠️ Нужно заполнить: {', '.join(missing.keys())}")
        else:
            log.info(f"  ✅ Все поля распознаны")

    # Сохраняем badge_mode из текущего state, чтобы не потерять его при set_state
    current_data = await state.get_data()
    badge_mode = current_data.get("badge_mode", False)

    # Сохраняем транзакции в состояние для подтверждения
    await state.set_state(ConfirmTransactionsState.transactions)
    await state.update_data(
        transactions=parsed_list,
        current_index=0,
        wizard_message_id=None,
        badge_mode=badge_mode,
    )
    
    # Показываем первую транзакцию для подтверждения
    await show_transaction_confirmation(parsed_list[0], message, state, 0, len(parsed_list))


@router.message(~StateFilter(default_state), F.text)
async def handle_natural_language(message: types.Message, state: FSMContext) -> None:
    """Текст вне default_state (мастер и пр.): NLU. В default_state запись операций идёт через financial_query → тот же NLU (без дубля)."""
    text = message.text.strip()
    
    # Пропускаем команды
    if text.startswith("/"):
        return
    
    # Пропускаем точные текстовые команды
    nlu_cfg = get_nlu_config()
    exact_commands = nlu_cfg.get("exact_commands", ["Синк Тинькофф"])
    if text in exact_commands:
        return
    
    # Пропускаем кнопки главного меню (они обрабатываются в start.py)
    menu_buttons = [
        "➖ Добавить расход",
        "➕ Добавить доход",
        "↔️ Перевод",
        "💼 Долги",
        "📈 Инвестиции",
        "📊 Баланс",
        "🧾 Последние операции",
        "📊 Суммаризация",
        "🔄 Синхронизация",
    ]
    if text in menu_buttons:
        log.info(f"🔘 Кнопка меню '{text}' - пропускаем (обрабатывается в start.py)")
        return  # Обрабатываются в start.py
    
    # Если пользователь в wizard - очищаем и обрабатываем как транзакцию через LLM
    current_state = await state.get_state()
    if current_state and current_state.startswith("AddTxnState"):
        log.info(f"📝 Текст получен в wizard состоянии {current_state} - ОЧИЩАЕМ и обрабатываем через LLM")
        await state.clear()
    
    # ВСЕ остальные текстовые сообщения передаем в LLM - он сам решит, транзакция это или нет
    log.info(f"📝 Обрабатываем текст через LLM: '{text}'")
    await _process_transactions(text, message, state)


@router.message(F.voice)
async def handle_voice_message(message: types.Message, state: FSMContext) -> None:
    """Обрабатывает голосовые сообщения"""
    # ПРОВЕРЯЕМ состояние и очищаем wizard, если нужно
    current_state = await state.get_state()
    log.info(f"🎤 Голосовое сообщение получено - ОСНОВНОЙ HANDLER. Текущее состояние: {current_state}")
    
    # ВСЕГДА очищаем wizard состояние, если есть
    if current_state:
        log.warning(f"⚠️ Обнаружено состояние {current_state} - ОЧИЩАЕМ")
        await state.clear()
    voice = message.voice
    
    # Скачиваем голосовое сообщение
    status_msg = await message.answer("🎤 Распознаю речь...")
    
    # Получаем файл
    file = await message.bot.get_file(voice.file_id)
    
    # Скачиваем во временный файл
    tmp_path = Path(tempfile.mktemp(suffix=".ogg"))
    try:
        await message.bot.download_file(file.file_path, destination=tmp_path)
        
        # Транскрибируем
        transcribed_text = transcribe_audio(tmp_path)
        
        if not transcribed_text:
            raise RuntimeError("ASR вернул пустой текст")
        
        # Показываем распознанный текст
        await status_msg.edit_text(f"🎤 Распознал: \"{transcribed_text}\"")
        
        log.info(f"🎤 Вызываем _process_transactions для голосового. Распознанный текст: '{transcribed_text}'")
        
        # Используем state, который уже есть в handler
        await _process_transactions(transcribed_text, message, state)
    except Exception as e:
        log.error("Voice processing failed: %s", e, exc_info=True)
        await status_msg.edit_text(f"❌ Ошибка обработки голоса:\n\n{str(e)}")
    finally:
        # Удаляем временный файл
        if tmp_path.exists():
            tmp_path.unlink()

