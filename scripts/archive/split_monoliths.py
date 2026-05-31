#!/usr/bin/env python3
"""One-off splitter for finance/knowledge/planning monoliths. Run from Agent root."""
from __future__ import annotations

from pathlib import Path

AGENT = Path(__file__).resolve().parent.parent


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def slc(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def split_transactions() -> None:
    src = AGENT / "finance_bot/bot/handlers/transactions.py"
    lines = read_lines(src)
    pkg = AGENT / "finance_bot/bot/handlers/transactions"
    pkg.mkdir(parents=True, exist_ok=True)
    svc = AGENT / "finance_bot/bot/services/transactions"
    svc.mkdir(parents=True, exist_ok=True)

    core = slc(lines, 31, 44) + "\n\n" + slc(lines, 469, 772)
    for old, new in [
        ("async def _get_or_create_account", "async def get_or_create_account"),
        ("async def _handle_broker_withdraw", "async def handle_broker_withdraw"),
        ("def _format_transaction_response", "def format_transaction_response"),
        ("async def _get_missing_fields", "async def get_missing_fields"),
        ("def _looks_like_transaction", "def looks_like_transaction"),
        ("def _parse_occurred_at", "def parse_occurred_at"),
        ("_parse_occurred_at(", "parse_occurred_at("),
    ]:
        core = core.replace(old, new)

    (svc / "core.py").write_text(
        '"""Transaction domain logic (NLU validation, accounts, parsing)."""\n'
        "from __future__ import annotations\n\n"
        "import logging\nfrom datetime import date, datetime, time\nfrom decimal import Decimal\n"
        "from typing import Optional\n\nfrom sqlalchemy import select\n\n"
        "from bot.db import AsyncSessionLocal\nfrom bot.models import User, Account, Transaction\n"
        "from bot.config_loader import get_nlu_config\nfrom bot.services.categories import load_categories\n\n"
        'log = logging.getLogger("finance.transactions")\n\n' + core,
        encoding="utf-8",
    )
    (svc / "__init__.py").write_text(
        "from bot.services.transactions.core import (\n"
        "    format_transaction_response,\n    get_missing_fields,\n"
        "    get_or_create_account,\n    handle_broker_withdraw,\n"
        "    looks_like_transaction,\n    parse_occurred_at,\n)\n\n"
        "__all__ = [\n"
        '    "format_transaction_response", "get_missing_fields", "get_or_create_account",\n'
        '    "handle_broker_withdraw", "looks_like_transaction", "parse_occurred_at",\n'
        "]\n",
        encoding="utf-8",
    )

    (pkg / "states.py").write_text(
        '"""FSM states for transaction wizards."""\nfrom aiogram.fsm.state import State, StatesGroup\n\n'
        + slc(lines, 47, 60),
        encoding="utf-8",
    )

    wh = slc(lines, 63, 106) + slc(lines, 109, 311)
    wh = wh.replace("_parse_occurred_at", "parse_occurred_at")
    (pkg / "wizard.py").write_text(
        '"""Manual add-expense/income wizard."""\nfrom __future__ import annotations\n\n'
        "import logging\nfrom datetime import datetime\nfrom decimal import Decimal\nfrom typing import List, Optional\n\n"
        "from aiogram import Router, types, F\nfrom aiogram.fsm.context import FSMContext\n"
        "from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup\nfrom sqlalchemy import select\n\n"
        "from bot.db import AsyncSessionLocal\nfrom bot.models import User, Account, Transaction\n"
        "from bot.services.categories import load_categories\nfrom bot.services.transactions import parse_occurred_at\n"
        "from bot.handlers.transactions.states import AddTxnState\n\n"
        'log = logging.getLogger("finance.transactions.wizard")\nrouter = Router()\n\n' + wh,
        encoding="utf-8",
    )

    (pkg / "balance.py").write_text(
        '"""Balance view."""\nfrom __future__ import annotations\n\n'
        "import logging\nfrom decimal import Decimal\nfrom typing import List, Tuple\n\n"
        "from aiogram import Router, types, F\nfrom aiogram.exceptions import TelegramBadRequest\n"
        "from aiogram.types import InlineKeyboardMarkup\nfrom sqlalchemy import select, func\n\n"
        "from bot.db import AsyncSessionLocal\nfrom bot.models import User, Account, Transaction\n"
        "from bot.services.badge_tracker import is_badge_account_name\n"
        "from bot.services.crypto_prices import fetch_prices_rub\n\n"
        'log = logging.getLogger("finance.transactions.balance")\nrouter = Router()\n\n'
        + slc(lines, 314, 466),
        encoding="utf-8",
    )

    conf = slc(lines, 776, 1025)
    conf = conf.replace("_get_missing_fields", "get_missing_fields").replace("_parse_occurred_at", "parse_occurred_at")
    (pkg / "confirmation.py").write_text(
        '"""Multi-transaction confirmation UI."""\nfrom __future__ import annotations\n\n'
        "import logging\nfrom datetime import datetime\nfrom decimal import Decimal\nfrom typing import Optional\n\n"
        "from aiogram.fsm.context import FSMContext\n"
        "from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message\nfrom sqlalchemy import select\n\n"
        "from bot.db import AsyncSessionLocal\nfrom bot.models import User, Account\n"
        "from bot.services.categories import load_categories\n"
        "from bot.services.transactions import get_missing_fields, parse_occurred_at\n\n"
        'log = logging.getLogger("finance.transactions.confirmation")\n\n' + conf,
        encoding="utf-8",
    )

    nlu = slc(lines, 1028, 1180).replace("async def _process_transactions", "async def process_transactions")
    nlu = nlu.replace("_get_missing_fields", "get_missing_fields")
    (pkg / "nlu.py").write_text(
        '"""NLU + voice handlers."""\nfrom __future__ import annotations\n\n'
        "import logging\nimport tempfile\nfrom pathlib import Path\nfrom typing import Optional\n\n"
        "from aiogram import Router, types, F\nfrom aiogram.filters import StateFilter\n"
        "from aiogram.fsm.context import FSMContext\nfrom aiogram.fsm.state import default_state\n\n"
        "from bot.config_loader import get_nlu_config\nfrom bot.services.asr import transcribe_audio\n"
        "from bot.services.nlu_parser import TransactionNLUParser\nfrom bot.services.transactions import get_missing_fields\n"
        "from bot.handlers.transactions.confirmation import show_transaction_confirmation\n"
        "from bot.handlers.transactions.states import AddTxnState, ConfirmTransactionsState\n\n"
        'log = logging.getLogger("finance.transactions.nlu")\nrouter = Router()\n\n' + nlu,
        encoding="utf-8",
    )

    (pkg / "__init__.py").write_text(
        '"""Transaction handlers package."""\nfrom aiogram import Router\n\n'
        "from bot.handlers.transactions.balance import _render_balance, router as balance_router\n"
        "from bot.handlers.transactions.confirmation import show_transaction_confirmation\n"
        "from bot.handlers.transactions.nlu import process_transactions, router as nlu_router\n"
        "from bot.handlers.transactions.states import AddTxnState, ConfirmTransactionsState\n"
        "from bot.handlers.transactions.wizard import add_expense_cb, add_income_cb, router as wizard_router\n"
        "from bot.services.transactions import get_or_create_account, handle_broker_withdraw, parse_occurred_at\n\n"
        "router = Router()\nrouter.include_router(wizard_router)\nrouter.include_router(balance_router)\nrouter.include_router(nlu_router)\n\n"
        "__all__ = [\n"
        '    "AddTxnState", "ConfirmTransactionsState", "add_expense_cb", "add_income_cb",\n'
        '    "get_or_create_account", "handle_broker_withdraw", "parse_occurred_at", "process_transactions",\n'
        '    "router", "show_transaction_confirmation", "_render_balance",\n'
        "]\n",
        encoding="utf-8",
    )
    src.unlink()
    print("transactions split OK")


def split_dashboard() -> None:
    src = AGENT / "finance_bot/scripts/build_finance_dashboard.py"
    lines = read_lines(src)
    pkg = AGENT / "finance_bot/bot/services/dashboard"
    pkg.mkdir(parents=True, exist_ok=True)
    charts_dir = AGENT / "shared/charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    (charts_dir / "__init__.py").write_text(
        "from shared.charts.mermaid import mermaid_pie, mermaid_xychart_lines\n\n"
        '__all__ = ["mermaid_pie", "mermaid_xychart_lines"]\n',
        encoding="utf-8",
    )
    mermaid_body = slc(lines, 285, 295) + "\n\n" + slc(lines, 402, 421)
    (charts_dir / "mermaid.py").write_text(
        '"""Mermaid chart snippets (Obsidian-compatible)."""\nfrom __future__ import annotations\n\n' + mermaid_body,
        encoding="utf-8",
    )

    (pkg / "charts.py").write_text(
        '"""Matplotlib PNG charts for finance dashboard."""\nfrom __future__ import annotations\n\n'
        "from pathlib import Path\nfrom typing import List, Optional\n\n" + slc(lines, 75, 199),
        encoding="utf-8",
    )
    (pkg / "data.py").write_text(
        '"""SQLite data loading for dashboard."""\nfrom __future__ import annotations\n\n'
        "import sqlite3\nfrom collections import defaultdict\nfrom datetime import datetime\n"
        "from decimal import Decimal\nfrom pathlib import Path\nfrom typing import Optional\n\n"
        "from bot.broker_portfolio import is_broker_portfolio_account\n\n"
        + slc(lines, 51, 72)
        + slc(lines, 202, 282),
        encoding="utf-8",
    )
    fmt = slc(lines, 355, 399)
    (pkg / "format.py").write_text(
        '"""Dashboard formatting helpers."""\nfrom __future__ import annotations\n\n'
        "from typing import Optional\n\n" + fmt,
        encoding="utf-8",
    )
    badge = slc(lines, 298, 352)
    badge = badge.replace("_fmt_num", "fmt_num").replace("plot_stacked_bar_categories_png", "plot_stacked_bar_categories_png")
    (pkg / "badge.py").write_text(
        '"""Badge nutrition dashboard section."""\nfrom __future__ import annotations\n\n'
        "import sqlite3\nfrom datetime import datetime\nfrom pathlib import Path\n\n"
        "from bot.config_loader import get_badge_config, is_badge_enabled\n"
        "from bot.services.badge_tracker import BadgeTracker\n"
        "from bot.services.dashboard.charts import plot_stacked_bar_categories_png\n"
        "from bot.services.dashboard.format import fmt_num\n\n" + badge.replace("_fmt_num", "fmt_num"),
        encoding="utf-8",
    )
    (pkg / "__init__.py").write_text(
        "from bot.services.dashboard.badge import build_badge_section\n"
        "from bot.services.dashboard.charts import plot_lines_png, plot_stacked_bar_categories_png\n"
        "from bot.services.dashboard.data import acc_balance, ensure_account_balance_snapshots_table, load_data, parse_datetime\n"
        "from bot.services.dashboard.format import fmt_num, pie_with_pct, safe_comment\n\n"
        "__all__ = [\n"
        '    "acc_balance", "build_badge_section", "ensure_account_balance_snapshots_table", "fmt_num",\n'
        '    "load_data", "parse_datetime", "pie_with_pct", "plot_lines_png",\n'
        '    "plot_stacked_bar_categories_png", "safe_comment",\n'
        "]\n",
        encoding="utf-8",
    )

    # main: header + find_vault + main body with imports fixed
    header = slc(lines, 1, 36)
    header = header.replace(
        "from bot.broker_portfolio import BROKER_PORTFOLIO_ACCOUNT_TYPE, is_broker_portfolio_account  # noqa: E402\n"
        "from bot.config_loader import get_badge_config, is_badge_enabled  # noqa: E402\n"
        "from bot.services.badge_tracker import BadgeTracker  # noqa: E402\n"
        "from bot.vault_paths import VaultPaths  # noqa: E402\n"
        "from shared.constants import finance_dashboard_start_date  # noqa: E402\n\n\n"
        "def find_vault_and_db(args) -> tuple[Path, Path, Path]:\n"
        '    """Возвращает (vault, db_path, out_path). Структура каталогов — bot.vault_paths.VaultPaths (+ env FINANCE_REL_*)."""\n'
        "    if args.vault:\n"
        "        vault = Path(args.vault).resolve()\n"
        "    else:\n"
        "        script_dir = Path(__file__).resolve().parent\n"
        "        vault = script_dir.parent.parent.parent.parent  # finance_bot -> Agent -> 800 -> Vault\n"
        "    vp = VaultPaths(vault)\n"
        "    db_path = args.db or vp.finance_db()\n"
        "    out_path = args.out or vp.finance_dashboard_md()\n"
        "    return vault, db_path, out_path\n\n\n",
        "from bot.services.dashboard import (\n"
        "    acc_balance,\n    build_badge_section,\n    ensure_account_balance_snapshots_table,\n"
        "    fmt_num,\n    load_data,\n    parse_datetime,\n    pie_with_pct,\n"
        "    plot_lines_png,\n    plot_stacked_bar_categories_png,\n    safe_comment,\n"
        ")\nfrom bot.vault_paths import VaultPaths  # noqa: E402\n"
        "from shared.charts.mermaid import mermaid_pie, mermaid_xychart_lines\n"
        "from shared.constants import finance_dashboard_start_date  # noqa: E402\n\n\n"
        "def find_vault_and_db(args) -> tuple[Path, Path, Path]:\n"
        '    """Возвращает (vault, db_path, out_path)."""\n'
        "    if args.vault:\n        vault = Path(args.vault).resolve()\n"
        "    else:\n        script_dir = Path(__file__).resolve().parent\n"
        "        vault = script_dir.parent.parent.parent.parent\n"
        "    vp = VaultPaths(vault)\n"
        "    return vault, args.db or vp.finance_db(), args.out or vp.finance_dashboard_md()\n\n\n",
    )
    main_body = slc(lines, 424, 1318)
    repl = [
        ("_ensure_account_balance_snapshots_table", "ensure_account_balance_snapshots_table"),
        ("_parse_datetime", "parse_datetime"),
        ("_build_badge_section", "build_badge_section"),
        ("_fmt_num", "fmt_num"),
        ("_safe_comment", "safe_comment"),
        ("_pie_with_pct", "pie_with_pct"),
        ("_external_rub_non_portfolio_total", "external_rub_non_portfolio_total"),
    ]
    for a, b in repl:
        main_body = main_body.replace(a, b)
    # external_rub function stays in main or move to data.py - it was in original at 215-234
    ext_fn = slc(lines, 215, 234).replace("_external_rub_non_portfolio_total", "external_rub_non_portfolio_total")
    log_fn = slc(lines, 1320, 1342).replace("_log", "log_dashboard")
    new_main = header + ext_fn + "\n\n" + main_body + "\n\n" + log_fn.replace("def _log", "def log_dashboard")
    new_main = new_main.replace("def main():", "def main() -> None:")
    new_main = new_main.replace("_log(", "log_dashboard(")
    src.write_text(new_main, encoding="utf-8")
    print("dashboard split OK")


def split_note_complete() -> None:
    src = AGENT / "knowledge_bot/app/handlers/note_complete.py"
    lines = read_lines(src)
    pkg = AGENT / "knowledge_bot/app/handlers/note_complete"
    pkg.mkdir(parents=True, exist_ok=True)

    imports = slc(lines, 1, 28)
    media = slc(lines, 40, 177)
    # dedupe: remove second ytdlp block 269-307 by not including in enrich
    enrich = slc(lines, 179, 267) + slc(lines, 308, 380)
    finalize = slc(lines, 382, 514)

    ytdlp_helper = '''
async def _ytdlp_fallback(cfg, routed, summary_obj, log):
    """Download large video via yt-dlp when Telegram file unavailable."""
    if os.environ.get("YTDLP_ENABLED", "0") != "1":
        return
    has_files = bool((routed.get("attachments", {}) or {}).get("files"))
    ytdlp_url = None
    if not has_files:
        for u in routed.get("attachments", {}).get("links", []) or []:
            if any(d in u for d in ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "x.com", "twitter.com")):
                ytdlp_url = u
                break
    if not ytdlp_url:
        return
    from knowledge_bot.services.extract import download_via_ytdlp, extract_from_path
    saved_path = download_via_ytdlp(ytdlp_url, cfg.export_root)
    if not saved_path:
        return
    try:
        rel = saved_path.relative_to(cfg.vault_path)
        routed["attachments"]["files"].append(str(rel))
        routed["raw_dir"] = str(rel.parent)
    except Exception:
        routed["attachments"]["files"].append(str(saved_path))
        routed["raw_dir"] = str(saved_path.parent)
    routed["form"] = routed.get("form") or "video"
    routed.setdefault("filenames", []).append(saved_path.name)
    try:
        asr_sem = get_asr_semaphore()
        async with asr_sem:
            derived = await asyncio.to_thread(extract_from_path, str(saved_path))
            import gc
            gc.collect()
        if derived.asr_text:
            existing = summary_obj["derived"].get("asr_text", "")
            summary_obj["derived"]["asr_text"] = (existing + "\\n" + derived.asr_text).strip() if existing else derived.asr_text
        if derived.vision_text:
            existing = summary_obj["derived"].get("vision_text", "")
            summary_obj["derived"]["vision_text"] = (existing + "\\n" + derived.vision_text).strip() if existing else derived.vision_text
    except Exception as e:
        log.warning("asr after ytdlp failed: %s", e)
'''

    (pkg / "media.py").write_text(
        imports + "\n\n" + ytdlp_helper + "\n\n" + media.replace(
            "    # Fallback for heavy video via yt-dlp when Telegram refuses to download large files\n    try:\n        if os.environ.get(\"YTDLP_ENABLED\", \"0\") == \"1\":",
            "    await _ytdlp_fallback(cfg, routed, summary_obj, log)\n    if False:  # legacy block removed\n        if os.environ.get(\"YTDLP_ENABLED\", \"0\") == \"1\":",
        ).split("    # Fallback for heavy video")[0].rstrip() + "\n",
        encoding="utf-8",
    )
    # Simpler: rewrite media.py cleanly
    (pkg / "media.py").write_text(
        imports + "\n\n" + ytdlp_helper + "\n\n"
        + slc(lines, 40, 137).rstrip() + "\n    await _ytdlp_fallback(cfg, routed, summary_obj, log)\n",
        encoding="utf-8",
    )

    (pkg / "enrich.py").write_text(
        imports + "\n\nasync def enrich_note(cfg, llm, routed, summary_obj, bundle, all_messages, yt_url, log):\n"
        '    """Naming, links, fields, tags."""\n' + enrich,
        encoding="utf-8",
    )

    (pkg / "finalize.py").write_text(
        imports + "\n\nasync def finalize_and_send(main_message, routed, summary_obj, rendered, review_text, media_group_id, processing_msg, log):\n"
        + finalize.replace("    log.info(\"Rendering note", "    pass  # rendered passed in\n    if False and log.info(\"Rendering"),
        encoding="utf-8",
    )

    (pkg / "__init__.py").write_text(
        imports + "\n\nfrom knowledge_bot.app.handlers.note_complete.media import _ytdlp_fallback\n"
        "from knowledge_bot.app.handlers.note_complete.enrich import enrich_note\n"
        "from knowledge_bot.app.handlers.note_complete.finalize import finalize_and_send\n\n"
        + slc(lines, 30, 39)
        + slc(lines, 40, 76).replace("    for msg in all_messages:", "    for msg in all_messages:  # media loop")
        ,
        encoding="utf-8",
    )
    print("note_complete partial - needs manual orchestrator fix")


def split_vault_maintenance() -> None:
    src = AGENT / "planning_bot/tools/vault_maintenance.py"
    lines = read_lines(src)
    pkg = AGENT / "planning_bot/tools/vault_maintenance"
    pkg.mkdir(parents=True, exist_ok=True)

    header = slc(lines, 1, 26)
    (pkg / "kanban_sort.py").write_text(
        header + "\n" + slc(lines, 28, 518),
        encoding="utf-8",
    )
    (pkg / "quarterly.py").write_text(
        header + "\n" + slc(lines, 520, 623),
        encoding="utf-8",
    )
    (pkg / "kanban_ids.py").write_text(
        header + "\n" + slc(lines, 625, 716),
        encoding="utf-8",
    )
    (pkg / "kanban_state.py").write_text(
        header + "\n" + slc(lines, 718, 873),
        encoding="utf-8",
    )
    run_body = slc(lines, 875, 1060)
    (pkg / "runner.py").write_text(
        header + "\nfrom planning_bot.tools.vault_maintenance.kanban_ids import add_ids_to_tasks\n"
        "from planning_bot.tools.vault_maintenance.kanban_sort import sort_kanban_tasks\n"
        "from planning_bot.tools.vault_maintenance.kanban_state import get_kanban_state, log_task_movements\n"
        "from planning_bot.tools.vault_maintenance.quarterly import sync_quarterly_focus\n\n" + run_body,
        encoding="utf-8",
    )
    (pkg / "__init__.py").write_text(
        "from planning_bot.tools.vault_maintenance.kanban_ids import add_ids_to_tasks\n"
        "from planning_bot.tools.vault_maintenance.kanban_sort import sort_kanban_tasks\n"
        "from planning_bot.tools.vault_maintenance.kanban_state import (\n"
        "    get_kanban_state,\n    get_task_category_by_id,\n    get_task_category_from_text,\n"
        "    get_task_id_from_text,\n    get_task_title_by_id,\n    log_task_movements,\n)\n"
        "from planning_bot.tools.vault_maintenance.quarterly import sync_quarterly_focus\n"
        "from planning_bot.tools.vault_maintenance.runner import run_all\n\n"
        "__all__ = [\n"
        '    "add_ids_to_tasks", "get_kanban_state", "get_task_category_by_id", "get_task_category_from_text",\n'
        '    "get_task_id_from_text", "get_task_title_by_id", "log_task_movements", "run_all",\n'
        '    "sort_kanban_tasks", "sync_quarterly_focus",\n'
        "]\n",
        encoding="utf-8",
    )
    (pkg / "__main__.py").write_text(
        '"""python -m planning_bot.tools.vault_maintenance"""\nimport sys\n'
        "from planning_bot.tools.vault_maintenance import add_ids_to_tasks, run_all\n\n"
        "if __name__ == '__main__':\n    import argparse\n"
        "    p = argparse.ArgumentParser()\n    p.add_argument('--ids-only', action='store_true')\n"
        "    a = p.parse_args()\n    sys.exit(0 if (add_ids_to_tasks() if a.ids_only else run_all()) else 1)\n",
        encoding="utf-8",
    )
    src.unlink()
    print("vault_maintenance split OK")


if __name__ == "__main__":
    split_transactions()
    split_dashboard()
    split_vault_maintenance()
    print("Done (note_complete: run pipeline migration separately if needed)")
