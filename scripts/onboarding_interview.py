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


def _mvp_categories_slot(locale: str) -> str:
    """Comma list for prompt slots from checked-in categories_mvp.*.example (no NLP)."""
    name = (
        "categories_mvp.ru.yaml.example"
        if locale.startswith("ru")
        else "categories_mvp.en.yaml.example"
    )
    path = _ROOT / "finance_bot" / "config" / name
    raw = path.read_text(encoding="utf-8") if path.is_file() else ""
    data = yaml.safe_load(raw) if raw else None
    if not isinstance(data, list) or not data:
        raise SystemExit(f"mvp categories file missing or not a list: {path}")
    tops: list[str] = []
    seen: set[str] = set()
    for item in data:
        s = str(item).strip()
        if not s:
            continue
        top = s.split("/", 1)[0].strip()
        if top and top not in seen:
            seen.add(top)
            tops.append(top)
    return ", ".join(tops)


def _tone_slot_for_index(idx: int, locale: str) -> str:
    en = ("concise, direct", "friendly, conversational", "detailed, formal")
    ru = ("коротко, по делу", "дружелюбно, разговорно", "подробно, формально")
    table = ru if locale.startswith("ru") else en
    if idx < 0 or idx >= len(table):
        raise SystemExit(f"tone choice index out of range: {idx}")
    return table[idx]


def _currency_from_choice_label(label: str) -> str:
    upper = label.upper()
    for cur in ("RUB", "USD", "EUR"):
        if upper.startswith(cur) or f"({cur}" in upper or upper == cur:
            return cur
    raise SystemExit(f"currency choice must be RUB/USD/EUR catalog label, got {label!r}")


def _resolve_choice_label(q: Any, raw: str, locale: str) -> tuple[int, str]:
    """Exact AskQuestion label only (no fuzzy). Prefer --choice N from the skill."""
    from shared.capabilities.onboarding_interview import choices_for

    choices = list(choices_for(q, locale))
    if not choices:
        raise SystemExit(f"{q.id}: not a choice question")
    text = (raw or "").strip()
    for i, c in enumerate(choices):
        if text == c:
            return i, c
    raise SystemExit(
        f"{q.id}: pass exact catalog string or --choice N (0-based). options={choices!r}"
    )


def _apply_answer(
    state: dict[str, Any],
    qid: str,
    raw: str,
    locale: str,
    *,
    choice_index: int | None = None,
    use_mvp: bool = False,
) -> None:
    q = question_by_id(qid)
    if q is None:
        raise SystemExit(f"unknown question id: {qid}")
    answers: dict[str, Any] = state.setdefault("answers", {})
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

    def _label_from_choice() -> tuple[int, str]:
        from shared.capabilities.onboarding_interview import choices_for

        choices = list(choices_for(q, locale))
        if choice_index is not None:
            if choice_index < 0 or choice_index >= len(choices):
                raise SystemExit(f"{qid}: --choice {choice_index} out of range 0..{len(choices)-1}")
            return choice_index, choices[choice_index]
        return _resolve_choice_label(q, raw, locale)

    if qid == "user_about":
        text = raw.strip()
        answers[qid] = text
        slots["AUTHOR_CONTEXT"] = text
        _write_user_profile(text, slots.get("USER_TONE", ""), locale)
    elif qid == "user_tone":
        idx, label = _label_from_choice()
        answers[qid] = label
        slots["USER_TONE"] = _tone_slot_for_index(idx, locale)
    elif qid == "finance_currency":
        _, label = _label_from_choice()
        answers[qid] = label
        slots["USER_CURRENCY"] = _currency_from_choice_label(label)
    elif qid == "finance_accounts":
        text = raw.strip()
        answers[qid] = text
        accs = _parse_accounts(text)
        slots["USER_ACCOUNTS"] = ", ".join(a["name"] for a in accs)
        state["_parsed_accounts"] = accs
        if str(state.get("telegram_id") or "").isdigit():
            _write_initial_accounts(state, accs, slots)
    elif qid == "finance_categories":
        # Dumb recorder: skill passes the final comma-list, or --mvp for checked-in MVP labels.
        if use_mvp:
            text = _mvp_categories_slot(locale)
        else:
            text = raw.strip()
            if not text:
                raise SystemExit(
                    "finance_categories: pass the comma-separated list, or --mvp "
                    "(skill interprets 'defaults' — CLI does not)"
                )
        answers[qid] = text
        slots["USER_CATEGORIES"] = text
    elif qid == "finance_opening_balances":
        text = raw.strip()
        answers[qid] = text
        base = state.get("_parsed_accounts") or _parse_accounts(
            state.get("answers", {}).get("finance_accounts", "")
        )
        accs = _parse_balances(text, base)
        state["_parsed_accounts"] = accs
        _write_initial_accounts(state, accs, slots)
    elif qid == "planning_task_examples":
        text = raw.strip()
        answers[qid] = text
        slots["USER_TASK_EXAMPLES"] = text
    elif qid == "planning_goals":
        text = raw.strip()
        answers[qid] = text
        slots["USER_GOALS"] = text
    elif qid == "knowledge_folders":
        text = raw.strip()
        answers[qid] = text
        slots["USER_VAULT_FOLDERS"] = text
    elif qid == "telegram_user_id":
        tid = re.sub(r"\D", "", raw)
        answers[qid] = tid
        state["telegram_id"] = tid
        if tid:
            from scripts.setup.env_tools import env_path, set_env_value

            set_env_value(env_path(_ROOT), "TELEGRAM_USER_ID", tid, force=True)
        _patch_initial_accounts_telegram(tid, state)
        accs = state.get("_parsed_accounts") or _parse_accounts(
            state.get("answers", {}).get("finance_accounts", "")
        )
        if accs and get_capabilities().module(MODULE_FINANCE):
            _write_initial_accounts(state, accs, slots)
    elif qid == "openrouter_api":
        key = raw.strip()
        answers[qid] = "(set)" if key else "(empty)"
        if key:
            from scripts.setup.env_tools import env_path, set_env_value

            set_env_value(env_path(_ROOT), "OPENROUTER_API_KEY", key)
        # empty = skill chose to omit; do not invent "skip" synonyms
    elif qid == "deploy_target":
        _, label = _label_from_choice()
        answers[qid] = label
        state["deploy_target"] = label
        state["deploy_mode"] = normalize_deploy_mode(label)
    elif qid == "deploy_ssh_host":
        host = ssh_host_sanitized(raw)
        answers[qid] = host
        if host:
            from scripts.setup.env_tools import env_path, set_env_value

            set_env_value(env_path(_ROOT), "SERVER", host, force=True)
            state["deploy_ssh_host"] = host
    elif qid == "deploy_vps_ack":
        _, label = _label_from_choice()
        answers[qid] = label
        state["deploy_success"] = True
    elif qid in ("deploy_local_ack", "deploy_vps_later_ack", "deploy_ssh_key_ready"):
        _, label = _label_from_choice()
        answers[qid] = label
        if qid == "deploy_ssh_key_ready":
            state["deploy_ssh_key_ready"] = label
    else:
        answers[qid] = raw.strip()

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
    tid = str(state.get("telegram_id") or "").strip()
    if _INITIAL_ACCOUNTS.is_file():
        cur = load_yaml(_INITIAL_ACCOUNTS, default={}) or {}
        if isinstance(cur, dict) and str(cur.get("telegram_id", "")).isdigit():
            tid = str(cur["telegram_id"])
    if not tid.isdigit():
        print("skip initial_accounts.yaml — set telegram_user_id first")
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
        "telegram_id": tid,
        "accounts": rows,
    }
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
    text = args.text or ""
    _apply_answer(
        state,
        args.id,
        text,
        loc,
        choice_index=args.choice,
        use_mvp=bool(args.mvp),
    )
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

    p_ans = sub.add_parser("answer", help="Save one answer (skill interprets user intent)")
    p_ans.add_argument("id")
    p_ans.add_argument(
        "text",
        nargs="?",
        default="",
        help="Exact value to store (or exact catalog choice label)",
    )
    p_ans.add_argument(
        "--choice",
        type=int,
        default=None,
        metavar="N",
        help="0-based index into catalog choices (preferred for kind=choice)",
    )
    p_ans.add_argument(
        "--mvp",
        action="store_true",
        help="finance_categories only: fill from categories_mvp.*.example",
    )

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
