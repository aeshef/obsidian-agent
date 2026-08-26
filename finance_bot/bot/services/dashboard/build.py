"""Build finance dashboard markdown from finance.db (library entry).

CLI: ``python -m bot...`` via ``finance_bot/scripts/build_finance_dashboard.py``.
"""

import argparse
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from shared.bootstrap import setup_bot

setup_bot("finance_bot")
from bot.broker_portfolio import BROKER_PORTFOLIO_ACCOUNT_TYPE, is_broker_portfolio_account  # noqa: E402
from shared.finance.currency import base_currency, is_base_currency  # noqa: E402
from bot.services.dashboard.assemble import (  # noqa: E402
    HERO_META_PLACEHOLDER,
    assemble_dashboard_markdown,
    fill_summary_hero,
    write_dashboard_md,
)
from bot.services.dashboard.badge import build_badge_section  # noqa: E402
from bot.services.dashboard.data import (  # noqa: E402
    acc_balance,
    ensure_account_balance_snapshots_table,
    load_data,
)
from bot.services.dashboard.filters import (  # noqa: E402
    resolve_badge_account_name,
    skip_badge_account,
)
from bot.services.dashboard.format import fmt_num  # noqa: E402
from bot.dashboard_templates import dtpl  # noqa: E402
from bot.vault_paths import VaultPaths  # noqa: E402
from bot.services.dashboard.cli import (  # noqa: E402
    build_arg_parser,
    find_vault_and_db,
    log_dashboard,
)


def run_build(args: argparse.Namespace) -> None:
    vault, db_path, out_path = find_vault_and_db(args)
    vp = VaultPaths(vault)
    charts_dir = vp.finance_charts_dir()
    vault_root = vault.resolve()

    def wikilink_png(png_path: Path) -> str:
        rel = png_path.resolve().relative_to(vault_root)
        return f"![[{rel.as_posix()}]]"

    log_file = Path(__file__).resolve().parents[2] / "logs" / "build_finance_dashboard.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_dashboard(f"vault={vault} db_path={db_path} exists={db_path.exists()}", log_file)

    if not db_path.exists():
        rel_db = db_path.relative_to(vault) if vault in db_path.parents else db_path
        body = dtpl("errors", "db_not_found", db_path=rel_db)
        write_dashboard_md(out_path, body)
        print(dtpl("errors", "db_not_found_log", out_path=out_path))
        return

    db_mtime = datetime.fromtimestamp(db_path.stat().st_mtime)
    # Lapse past-month plans on canonical and dashboard DB separately (no full mirror —
    # replica may diverge on balances; we only need planned_expenses.status in sync).
    try:
        from bot.finance_db_paths import resolve_canonical_write_db
        from bot.services.month_plan import lapse_past_planned_sqlite

        today = datetime.now().date()
        for path in {db_path.resolve(), resolve_canonical_write_db().resolve()}:
            if not path.is_file():
                continue
            cconn = sqlite3.connect(path)
            n = lapse_past_planned_sqlite(cconn, today=today, user_id=args.user_id)
            cconn.close()
            if n:
                print(f"lapsed {n} past planned_expenses in {path.name}")
    except Exception as e:
        print(f"planned lapse skipped: {e}")

    accounts, transactions, planned = load_data(db_path, args.user_id)
    now = datetime.now()
    print(dtpl("logs", "loaded", accounts=len(accounts), transactions=len(transactions), planned=len(planned)))

    conn = sqlite3.connect(db_path)
    ensure_account_balance_snapshots_table(conn)
    cur = conn.cursor()

    # Broker balance snapshots by day (one row per sync)
    broker_snapshots: dict[int, list[tuple[datetime.date, float]]] = defaultdict(list)
    try:
        cur.execute(
            """SELECT s.account_id, s.snapshot_date, s.balance
               FROM account_balance_snapshots s
               JOIN accounts a ON a.id = s.account_id
               WHERE a.user_id = ? AND a.type = ?""",
            (args.user_id, BROKER_PORTFOLIO_ACCOUNT_TYPE),
        )
        for row in cur.fetchall():
            aid, sd, bal = row[0], row[1], float(row[2])
            d = sd if isinstance(sd, date) else datetime.strptime(str(sd)[:10], "%Y-%m-%d").date()
            broker_snapshots[aid].append((d, bal))
        for aid in broker_snapshots:
            broker_snapshots[aid].sort(key=lambda x: x[0])
    except sqlite3.OperationalError:
        pass  # table may not exist in old DB

    # Current balances
    acc_by_id = {a["id"]: a for a in accounts}
    balances_now = {}
    for a in accounts:
        balances_now[a["id"]] = acc_balance(cur, a["id"], bool(a["is_external_balance"]), a["external_balance"])

    _badge_acc_name = resolve_badge_account_name()

    total_rub = sum(
        float(b) for aid, b in balances_now.items()
        if is_base_currency(acc_by_id[aid]["currency"])
        and not skip_badge_account(aid, acc_by_id, _badge_acc_name)
    )
    total_usd = sum(
        float(b) for aid, b in balances_now.items()
        if acc_by_id[aid]["currency"] == "USD"
    )

    # Dashboard sections (assembled at end)
    part_summary = []
    part_planned = []
    part_structure = []
    part_exp_pies = []
    part_moves = []
    part_day_flow = []
    part_day_regular = []
    part_day_oneoff = []
    part_oneoff_list = []
    part_monthly = []
    part_quarterly = []
    part_exp_by_account = []
    part_balances = []
    part_top_exp = []
    part_total_balance = []
    part_badge = []

    cushion_runway_str = ""  # cash / essentials — filled in month-plan block
    # Summary hero — balances + runway filled later when spend avg is known.
    _summary_mtime = db_mtime.strftime("%Y-%m-%d %H:%M")
    part_summary.extend([
        dtpl("sections", "summary", "heading"),
        "",
    ])
    db_age_days = (datetime.now() - db_mtime).total_seconds() / 86400
    if db_age_days > 1:
        part_summary.append(
            dtpl("sections", "summary", "stale_data", mtime=_summary_mtime)
        )
    _hero_open = dtpl("sections", "summary", "hero_open")
    if _hero_open.strip():
        # Numbers as metric cards — filled after month-plan cushion is known
        part_summary.append(HERO_META_PLACEHOLDER)
        part_summary.append(f"_{_summary_mtime}_")
        part_summary.append("")
    else:
        part_summary.append(dtpl("sections", "summary", "db_updated", mtime=_summary_mtime))
        part_summary.append(
            dtpl("sections", "summary", "total_rub", amount=fmt_num(total_rub, decimals=2))
        )
        if total_usd != 0:
            part_summary.append(dtpl("sections", "summary", "total_usd", amount=fmt_num(total_usd, decimals=2)))
        part_summary.append("")

    # Planned expenses live inside month plan (one place). Past-month rows are
    # lapsed to status=expired in load_data — no separate dump section.
    try:
        from bot.services.month_plan import (
            build_month_plan,
            compute_balance_safety,
            compute_economic_month,
            inferred_from_config,
            load_month_plan_config,
            load_subscriptions,
            month_plan_config_path,
            planned_for_month,
            planned_upcoming,
            resolve_savings_buffer,
            soft_cap_overages,
            soft_caps_from_config,
            subscriptions_yaml_path,
        )

        cfg_path = month_plan_config_path()
        mp_cfg = load_month_plan_config(cfg_path)
        ym = f"{now.year:04d}-{now.month:02d}"
        income = float(mp_cfg.get("income_expected_rub") or 0)
        buffer, savings_rate = resolve_savings_buffer(mp_cfg, income)
        try:
            emergency_months = float(mp_cfg.get("emergency_months_target") or 3)
        except (TypeError, ValueError):
            emergency_months = 3.0
        inferred = inferred_from_config(mp_cfg)
        subs = load_subscriptions(subscriptions_yaml_path())
        specifics = planned_for_month(planned, ym)
        upcoming = planned_upcoming(planned, ym)
        econ = compute_economic_month(transactions, ym)
        recurring_sum = sum(x.amount for x in subs) + sum(x.amount for x in inferred)
        # Flexible burn = economic net spend minus budgeted recurring (already in commitment).
        flexible_spent = max(0.0, float(econ.economic_spend) - float(recurring_sum))
        snap = build_month_plan(
            ym=ym,
            today=now.date(),
            income_expected=income,
            subscriptions=subs,
            specifics=specifics,
            inferred=inferred,
            buffer_savings=buffer,
            savings_rate_pct=savings_rate,
            flexible_spent=flexible_spent,
        )
        flexible_left = max(0.0, float(snap.flexible_pool) - float(snap.flexible_spent))
        soft_caps = soft_caps_from_config(mp_cfg)
        overages = soft_cap_overages(econ.by_category, soft_caps)

        broker_ids = {
            a["id"]
            for a in accounts
            if is_base_currency(a.get("currency"))
            and is_broker_portfolio_account(a.get("type"), bool(a.get("is_external_balance")))
        }
        broker_rub = sum(float(balances_now.get(aid, 0) or 0) for aid in broker_ids)
        spendable_rub = float(total_rub) - broker_rub
        safety = compute_balance_safety(
            cash_rub=spendable_rub,
            broker_rub=broker_rub,
            planned=specifics,
            recurring=list(subs) + list(inferred),
            emergency_target_months=emergency_months,
            month_spent=float(econ.economic_spend),
        )
        cushion_runway_str = f"{safety.runway_months:.1f}"

        part_planned.extend([dtpl("sections", "month_plan", "heading"), ""])
        note = dtpl("sections", "month_plan", "gauges_note")
        if note:
            part_planned.extend([note, ""])

        from shared.obsidian_metric_cards import MetricCard, metric_cards_lines

        inv = float(econ.investments)
        buffer_status = ""
        if buffer > 0:
            if inv >= buffer * 0.9:
                b_accent, b_status_key = "#43a047", "buffer_status_ahead"
            elif inv >= buffer * 0.4:
                b_accent, b_status_key = "#1e88e5", "buffer_status_ok"
            else:
                b_accent, b_status_key = "#ffa726", "buffer_status_low"
            buffer_status = dtpl("sections", "month_plan", b_status_key) or b_status_key
        else:
            b_accent = "#90a4ae"

        free_accent = (
            "#e53935"
            if income > 0 and (flexible_left <= 0 or snap.burn_pct >= 100)
            else "#43a047"
        )
        cushion_accent = (
            "#e53935"
            if safety.runway_months < safety.emergency_target_months
            else "#7e57c2"
        )

        cards: list[MetricCard] = [
            MetricCard(
                label=dtpl("sections", "month_plan", "card_spent_label") or "Spent",
                value=f"{fmt_num(econ.economic_spend, decimals=0)} {base_currency()}",
                accent="#e53935",
                hint=dtpl(
                    "sections",
                    "month_plan",
                    "card_spent_hint",
                    gross=fmt_num(econ.consumption_gross, decimals=0),
                    reimb=fmt_num(econ.reimbursements, decimals=0),
                ),
            ),
        ]
        if income > 0:
            cards.append(
                MetricCard(
                    label=dtpl("sections", "month_plan", "card_free_label") or "Free",
                    value=f"{fmt_num(flexible_left, decimals=0)} {base_currency()}",
                    accent=free_accent,
                    hint=dtpl(
                        "sections",
                        "month_plan",
                        "card_free_hint",
                        pool=fmt_num(snap.flexible_pool, decimals=0),
                        burn=fmt_num(snap.burn_pct, decimals=0),
                    ),
                )
            )
            cards.append(
                MetricCard(
                    label=dtpl("sections", "month_plan", "card_daily_label") or f"{base_currency()}/day",
                    value=f"{fmt_num(snap.daily_allowance_remaining, decimals=0)} {base_currency()}",
                    accent="#1e88e5",
                    hint=dtpl(
                        "sections",
                        "month_plan",
                        "card_daily_hint",
                        days=snap.days_left,
                    ),
                )
            )
        if buffer > 0:
            cards.append(
                MetricCard(
                    label=dtpl("sections", "month_plan", "card_buffer_label") or "Savings",
                    value=f"{fmt_num(inv, decimals=0)} / {fmt_num(buffer, decimals=0)}",
                    accent=b_accent,
                    hint=dtpl(
                        "sections",
                        "month_plan",
                        "card_buffer_hint",
                        rate=fmt_num(savings_rate, decimals=0),
                        status=buffer_status,
                    ),
                )
            )
        cards.append(
            MetricCard(
                label=dtpl("sections", "month_plan", "card_cushion_label") or "Cushion",
                value=dtpl(
                    "sections",
                    "month_plan",
                    "card_cushion_value",
                    months=fmt_num(safety.runway_months, decimals=1),
                ) or f"{fmt_num(safety.runway_months, decimals=1)} mo",
                accent=cushion_accent,
                hint=dtpl(
                    "sections",
                    "month_plan",
                    "card_cushion_hint",
                    cash=fmt_num(safety.cash_rub, decimals=0),
                    broker=fmt_num(safety.broker_rub, decimals=0),
                ),
            )
        )
        part_planned.extend(metric_cards_lines(cards))

        if income <= 0:
            part_planned.append(dtpl("sections", "month_plan", "skip_income_zero"))
            part_planned.append("")

        # Soft caps (text tip — not a number row)
        part_planned.append(dtpl("sections", "month_plan", "soft_open") or "> [!tip] Soft cuts")
        if overages:
            for row in overages[:4]:
                part_planned.append(
                    dtpl(
                        "sections",
                        "month_plan",
                        "soft_line",
                        category=row["category"],
                        spent=fmt_num(row["spent"], decimals=0),
                        cap=fmt_num(row["cap"], decimals=0),
                        over=fmt_num(row["over"], decimals=0),
                    )
                )
        else:
            part_planned.append(
                dtpl("sections", "month_plan", "soft_empty") or "> - Within soft caps."
            )
        part_planned.append("")

        if specifics:
            part_planned.extend(["", dtpl("sections", "month_plan", "specifics_heading")])
            for sp in specifics:
                part_planned.append(
                    dtpl(
                        "sections",
                        "month_plan",
                        "specifics_line",
                        name=sp.name,
                        amount=fmt_num(sp.amount, decimals=0),
                        currency=sp.currency,
                    )
                )
        if upcoming:
            part_planned.extend(["", dtpl("sections", "month_plan", "upcoming_heading")])
            for sp, due in upcoming:
                part_planned.append(
                    dtpl(
                        "sections",
                        "month_plan",
                        "upcoming_line",
                        name=sp.name,
                        amount=fmt_num(sp.amount, decimals=0),
                        currency=sp.currency,
                        due=due.isoformat(),
                    )
                )
        part_planned.extend(["", dtpl("sections", "month_plan", "hint"), ""])

        # Optional LLM narrative (cached; never blocks dashboard on failure)
        try:
            from bot.services.dashboard_insight import generate_dashboard_month_insight

            top_cats = sorted(
                econ.by_category.items(), key=lambda kv: -kv[1]
            )[:6]
            protect = {
                str(x).strip()
                for x in (mp_cfg.get("insight_protect_names") or [])
                if str(x).strip()
            }
            do_not_cut = [x.name for x in inferred if x.name in protect]
            facts = {
                "ym": ym,
                "notes": (
                    "Transfers and broker top-ups are not consumption. "
                    "Non-salary income offsets group pays (reimbursements)."
                ),
                "economic": econ.to_dict(),
                "plan": {
                    "income_expected": income,
                    "savings_rate_pct": savings_rate,
                    "buffer_goal": buffer,
                    "buffer_deposited": round(inv, 2),
                    "buffer_status": buffer_status or "n/a",
                    "flexible_pool": snap.flexible_pool,
                    "flexible_spent": snap.flexible_spent,
                    "flexible_left": round(flexible_left, 2),
                    "burn_pct": snap.burn_pct,
                    "daily_left": snap.daily_allowance_remaining,
                    "days_left": snap.days_left,
                    "recurring_budget": recurring_sum,
                },
                "soft_overages": overages,
                "safety": safety.to_dict(),
                "top_categories": [
                    {"category": c, "amount": round(a, 0)} for c, a in top_cats
                ],
                "do_not_cut": do_not_cut,
                "salary_received": econ.salary_income,
            }
            tip_md = generate_dashboard_month_insight(vault, facts)
            if tip_md:
                part_planned.extend([tip_md.rstrip(), ""])
        except Exception as e:
            print(f"dashboard month insight skipped: {e}")
    except Exception as e:
        print(f"month_plan section skipped: {e}")

    from bot.services.dashboard.analytics_sections import build_analytics_sections

    _analytics = build_analytics_sections(
        now=now,
        accounts=accounts,
        transactions=transactions,
        planned=planned,
        balances_now=balances_now,
        acc_by_id=acc_by_id,
        broker_snapshots=broker_snapshots,
        conn=conn,
        cur=cur,
        charts_dir=charts_dir,
        vault_root=vault_root,
        badge_acc_name=_badge_acc_name,
        args_user_id=args.user_id,
        total_rub=float(total_rub),
    )
    part_structure = _analytics["part_structure"]
    part_exp_pies = _analytics["part_exp_pies"]
    part_moves = _analytics["part_moves"]
    part_day_flow = _analytics["part_day_flow"]
    part_day_regular = _analytics["part_day_regular"]
    part_day_oneoff = _analytics["part_day_oneoff"]
    part_oneoff_list = _analytics["part_oneoff_list"]
    part_monthly = _analytics["part_monthly"]
    part_quarterly = _analytics["part_quarterly"]
    part_exp_by_account = _analytics["part_exp_by_account"]
    part_balances = _analytics["part_balances"]
    part_top_exp = _analytics["part_top_exp"]
    part_total_balance = _analytics["part_total_balance"]

    # Hero: metric cards (same visual language as cockpit signals)
    fill_summary_hero(
        part_summary,
        total_rub=total_rub,
        total_usd=total_usd,
        cushion_runway_str=cushion_runway_str,
    )

    _badge_raw = build_badge_section(conn, args.user_id, charts_dir, now, chart_wikilink=wikilink_png)
    # Drop redundant ### heading when badge body sits inside a titled callout
    if _badge_raw and _badge_raw[0].startswith("###"):
        _badge_raw = _badge_raw[2:] if len(_badge_raw) > 2 and _badge_raw[1] == "" else _badge_raw[1:]
    part_badge.extend(_badge_raw)

    conn.close()

    body = assemble_dashboard_markdown(
        part_summary=part_summary,
        part_structure=part_structure,
        part_planned=part_planned,
        part_exp_pies=part_exp_pies,
        part_day_flow=part_day_flow,
        part_total_balance=part_total_balance,
        part_monthly=part_monthly,
        part_quarterly=part_quarterly,
        part_day_regular=part_day_regular,
        part_badge=part_badge,
        part_day_oneoff=part_day_oneoff,
        part_oneoff_list=part_oneoff_list,
        part_moves=part_moves,
        part_exp_by_account=part_exp_by_account,
        part_balances=part_balances,
        part_top_exp=part_top_exp,
    )
    write_dashboard_md(out_path, body)
    print(dtpl("logs", "written", out_path=out_path))





# Re-exports for callers that import from build
__all__ = ["build_arg_parser", "find_vault_and_db", "log_dashboard", "run_build"]
