#!/usr/bin/env python3
"""Onboarding interview CLI — list questions, apply answers, track completion."""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.setup.load_env import load_repo_env

load_repo_env(_ROOT)

from shared.agent.config import agent_config_dir
from shared.capabilities.onboarding_completion import completion_report
from shared.capabilities.onboarding_deploy import (
    deploy_hint_lines,
    deploy_mode,
    iter_visible_questions,
    normalize_deploy_mode,
    ssh_host_sanitized,
)
from shared.capabilities.onboarding_interview import (
    choices_for,
    prompt_for,
    question_by_id,
    questions_for_profile,
)
from shared.capabilities.profile import MODULE_FINANCE, clear_capabilities_cache, get_capabilities
from shared.yaml_config import load_yaml

_STATE_NAME = "onboarding_state.yaml"
_SLOTS_NAME = "onboarding_slots.yaml"
_PROFILE_NAME = "user_profile.md"
_INITIAL_ACCOUNTS = _ROOT / "finance_bot" / "config" / "initial_accounts.yaml"


def _resolve_locale(raw: str | None) -> str:
    import os

    loc = (raw or os.environ.get("AGENT_LOCALE") or "en").strip().lower()
    return "ru" if loc.startswith("ru") else "en"


def _state_path() -> Path:
    return agent_config_dir() / _STATE_NAME


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {"completed": [], "answers": {}}
    data = load_yaml(path, default={}) or {}
    if not isinstance(data, dict):
        return {"completed": [], "answers": {}}
    data.setdefault("completed", [])
    data.setdefault("answers", {})
    return data


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(state, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _parse_accounts(text: str) -> list[dict[str, Any]]:
    names: list[str] = []
    for part in re.split(r"[\n,;]+", text or ""):
        name = part.strip().strip("-•*")
        if name:
            names.append(name)
    out: list[dict[str, Any]] = []
    for name in names:
        low = name.lower()
        acc_type = "wallet" if any(h in low for h in ("cash", "налич", "нал")) else "card"
        out.append({"name": name, "type": acc_type, "balance": 0, "currency": "RUB"})
    return out


def _parse_balances(text: str, accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {a["name"].lower(): dict(a) for a in accounts}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        name, _, rest = line.partition(":")
        key = name.strip().lower()
        amount_s = re.sub(r"[^\d.,\-]", "", rest.replace(",", "."))
        try:
            bal = Decimal(amount_s) if amount_s else Decimal(0)
        except InvalidOperation:
            bal = Decimal(0)
        matched = None
        for k, acc in by_name.items():
            if k == key or key in k or k in key:
                matched = acc
                break
        if matched is not None:
            matched["balance"] = float(bal)
    return list(by_name.values())


def _choice_to_tone(choice: str, locale: str) -> str:
    c = choice.strip().lower()
    if locale == "ru":
        if "корот" in c or "делу" in c:
            return "коротко, по делу"
        if "друж" in c:
            return "дружелюбно, разговорно"
        return "подробно, формально"
    if "short" in c or "direct" in c:
        return "concise, direct"
    if "friend" in c:
        return "friendly, conversational"
    return "detailed, formal"


def _choice_to_currency(choice: str) -> str:
    for cur in ("RUB", "USD", "EUR"):
        if cur in choice.upper():
            return cur
    return "RUB"


def _apply_answer(state: dict[str, Any], qid: str, raw: str, locale: str) -> None:
    q = question_by_id(qid)
    if q is None:
        raise SystemExit(f"unknown question id: {qid}")
    answers: dict[str, Any] = state.setdefault("answers", {})
    answers[qid] = raw.strip()
    completed: list[str] = list(state.setdefault("completed", []))
    if qid not in completed:
        completed.append(qid)
    state["completed"] = completed

    slots_path = agent_config_dir() / _SLOTS_NAME
    slots: dict[str, str] = {}
    if slots_path.is_file():
        loaded = load_yaml(slots_path, default={}) or {}
        if isinstance(loaded, dict):
            slots = {str(k): str(v) for k, v in loaded.items()}

    slots["USER_LOCALE"] = locale

    if qid == "user_about":
        slots["AUTHOR_CONTEXT"] = raw.strip()
        _write_user_profile(raw.strip(), slots.get("USER_TONE", ""), locale)
    elif qid == "user_tone":
        slots["USER_TONE"] = _choice_to_tone(raw, locale)
    elif qid == "finance_currency":
        slots["USER_CURRENCY"] = _choice_to_currency(raw)
    elif qid == "finance_accounts":
        accs = _parse_accounts(raw)
        slots["USER_ACCOUNTS"] = ", ".join(a["name"] for a in accs)
        state["_parsed_accounts"] = accs
        _write_initial_accounts(state, accs, slots)
    elif qid == "finance_categories":
        low = raw.strip().lower()
        if low in ("по умолчанию", "пропустить", "пропуск", "default", "skip", "mvp", "defaults"):
            slots["USER_CATEGORIES"] = (
                "Еда, Транспорт, Дом, Развлечения"
                if locale.startswith("ru")
                else "Food, Transport, Housing, Groceries, Fun"
            )
        else:
            slots["USER_CATEGORIES"] = raw.strip() or slots.get("USER_CATEGORIES", "")
    elif qid == "finance_opening_balances":
        base = state.get("_parsed_accounts") or _parse_accounts(
            state.get("answers", {}).get("finance_accounts", "")
        )
        accs = _parse_balances(raw, base)
        state["_parsed_accounts"] = accs
        _write_initial_accounts(state, accs, slots)
    elif qid == "planning_task_examples":
        slots["USER_TASK_EXAMPLES"] = raw.strip()
    elif qid == "planning_goals":
        slots["USER_GOALS"] = raw.strip()
    elif qid == "knowledge_folders":
        slots["USER_VAULT_FOLDERS"] = raw.strip()
    elif qid == "telegram_user_id":
        tid = re.sub(r"\D", "", raw)
        state["telegram_id"] = tid
        _patch_initial_accounts_telegram(tid, state)
    elif qid == "openrouter_api":
        from scripts.setup.env_tools import set_env_value, env_path

        key = raw.strip()
        if key and not key.lower().startswith("skip"):
            set_env_value(env_path(_ROOT), "OPENROUTER_API_KEY", key)
    elif qid == "deploy_target":
        state["deploy_target"] = raw.strip()
        state["deploy_mode"] = normalize_deploy_mode(raw)
    elif qid == "deploy_ssh_host":
        host = ssh_host_sanitized(raw)
        if host:
            from scripts.setup.env_tools import env_path, set_env_value

            set_env_value(env_path(_ROOT), "SERVER", host, force=True)
            state["deploy_ssh_host"] = host
    elif qid == "deploy_ssh_key_ready":
        state["deploy_ssh_key_ready"] = raw.strip()
    elif qid == "deploy_vps_ack":
        low = raw.strip().lower()
        if any(k in low for k in ("yes", "да", "up", "работает", "works")):
            state["deploy_success"] = True
        else:
            state["deploy_deferred"] = True

    _dump_slots(slots_path, slots)


def _write_user_profile(about: str, tone: str, locale: str) -> None:
    path = agent_config_dir() / _PROFILE_NAME
    if path.is_file():
        cur = path.read_text(encoding="utf-8").strip()
        if len(cur) > 80 and "..." not in cur[:30]:
            return
    if locale == "ru":
        body = f"""# Профиль пользователя

## Кто я
{about}

## Как со мной общаться
- {tone or 'коротко, по делу'}
"""
    else:
        body = f"""# User profile

## About me
{about}

## Communication
- {tone or 'concise, friendly'}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(_ROOT)}")


def _dump_slots(path: Path, slots: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(slots, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"wrote {path.relative_to(_ROOT)}")


def _write_initial_accounts(
    state: dict[str, Any],
    accounts: list[dict[str, Any]],
    slots: dict[str, str],
) -> None:
    prof = get_capabilities()
    if not prof.module(MODULE_FINANCE):
        return
    currency = slots.get("USER_CURRENCY", "RUB")
    rows: list[dict[str, Any]] = []
    for a in accounts:
        rows.append(
            {
                "name": a["name"],
                "balance": a.get("balance", 0),
                "currency": a.get("currency") or currency,
                "type": a.get("type") or "card",
            }
        )
    doc: dict[str, Any] = {
        "telegram_id": state.get("telegram_id") or "YOUR_TELEGRAM_NUMERIC_ID",
        "accounts": rows,
    }
    if _INITIAL_ACCOUNTS.is_file():
        cur = load_yaml(_INITIAL_ACCOUNTS, default={}) or {}
        if isinstance(cur, dict) and str(cur.get("telegram_id", "")).isdigit():
            doc["telegram_id"] = cur["telegram_id"]
    _INITIAL_ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
    _INITIAL_ACCOUNTS.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"wrote {_INITIAL_ACCOUNTS.relative_to(_ROOT)}")


def _patch_initial_accounts_telegram(tid: str, state: dict[str, Any]) -> None:
    if not tid:
        return
    accs = state.get("_parsed_accounts")
    if _INITIAL_ACCOUNTS.is_file():
        doc = load_yaml(_INITIAL_ACCOUNTS, default={}) or {}
        if not isinstance(doc, dict):
            doc = {}
    else:
        doc = {"accounts": accs or []}
    doc["telegram_id"] = int(tid)
    if accs and not doc.get("accounts"):
        doc["accounts"] = accs
    _INITIAL_ACCOUNTS.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"patched telegram_id in {_INITIAL_ACCOUNTS.relative_to(_ROOT)}")


def cmd_list(args: argparse.Namespace) -> int:
    clear_capabilities_cache()
    prof = get_capabilities()
    loc = _resolve_locale(args.locale)
    state = _load_state()
    qs = iter_visible_questions(prof, phase=args.phase, locale=loc, state=state)
    done = set(state.get("completed") or [])
    for q in qs:
        mark = "✓" if q.id in done else " "
        print(f"[{mark}] {q.id}\t{prompt_for(q, loc)}")
        ch = choices_for(q, loc)
        if ch:
            for i, c in enumerate(ch, 1):
                print(f"      {i}. {c}")
    return 0


def cmd_answer(args: argparse.Namespace) -> int:
    loc = _resolve_locale(args.locale)
    state = _load_state()
    _apply_answer(state, args.id, args.text, loc)
    _save_state(state)
    print(f"saved answer: {args.id}")
    return 0


def cmd_apply_json(args: argparse.Namespace) -> int:
    loc = _resolve_locale(args.locale)
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    answers = data.get("answers") if isinstance(data, dict) else data
    if not isinstance(answers, dict):
        raise SystemExit("JSON must be {answers: {id: text}}")
    state = _load_state()
    for qid, text in answers.items():
        _apply_answer(state, str(qid), str(text), loc)
    _save_state(state)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    clear_capabilities_cache()
    loc = _resolve_locale(args.locale)
    errors, warnings = completion_report(strict_interview=bool(getattr(args, "strict", False)))
    print("=== onboarding status ===")
    for w in warnings:
        print(f"  warn: {w}")
    for e in errors:
        print(f"  ERR: {e}")
    if errors:
        return 1
    print("READY" if not warnings else "OK (warnings)")
    return 0


def cmd_confirm_bot(args: argparse.Namespace) -> int:
    state = _load_state()
    state["bot_smoke_confirmed"] = True
    _save_state(state)
    print("bot_smoke_confirmed")
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    clear_capabilities_cache()
    loc = _resolve_locale(args.locale)
    prof = get_capabilities()
    state = _load_state()
    done = set(state.get("completed") or [])
    for phase in ("intro", "before_layout", "after_layout", "after_secrets", "finalize"):
        for q in iter_visible_questions(prof, phase=phase, locale=loc, state=state):
            if q.id in done:
                continue
            payload: dict[str, Any] = {
                "id": q.id,
                "phase": q.phase,
                "prompt": prompt_for(q, loc),
                "kind": q.kind,
            }
            if q.phase == "finalize" and q.id == "deploy_target":
                payload["hint"] = deploy_hint_lines(state, loc)
            ch = choices_for(q, loc)
            if ch:
                payload["choices"] = list(ch)
            print(json.dumps(payload, ensure_ascii=False))
            return 0
    print(json.dumps({"done": True, "deploy_mode": deploy_mode(state)}))
    return 0


def cmd_deploy_hint(args: argparse.Namespace) -> int:
    loc = _resolve_locale(args.locale)
    state = _load_state()
    mode = deploy_mode(state) or "unknown"
    print(f"deploy_mode={mode}")
    for line in deploy_hint_lines(state, loc):
        print(line)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--locale", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List interview questions")
    p_list.add_argument("--phase", default=None)

    p_ans = sub.add_parser("answer", help="Save one answer")
    p_ans.add_argument("id")
    p_ans.add_argument("text")

    p_json = sub.add_parser("apply-json", help="Apply answers from JSON file")
    p_json.add_argument("file")

    p_status = sub.add_parser("status", help="Completion checklist")
    p_status.add_argument("--strict", action="store_true")

    sub.add_parser("next", help="Next unanswered question as JSON")

    p_check = sub.add_parser("check", help="Alias for status --strict")
    p_check.add_argument("--strict", action="store_true", default=True)

    sub.add_parser("confirm-bot", help="Mark live Telegram smoke as done")

    sub.add_parser("deploy-hint", help="Print deploy checklist from onboarding state")

    args = ap.parse_args()
    if args.cmd == "check":
        args.strict = True
        args.cmd = "status"
    handlers = {
        "list": cmd_list,
        "answer": cmd_answer,
        "apply-json": cmd_apply_json,
        "status": cmd_status,
        "next": cmd_next,
        "confirm-bot": cmd_confirm_bot,
        "deploy-hint": cmd_deploy_hint,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
