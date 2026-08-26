"""Connector playbooks for guided onboarding (no secrets, no personal paths)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shared.capabilities.profile import (
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_DOMESTIC_BANK_CARDS,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_KB_SERENDIPITY,
    CONNECTOR_MAC_CONTEXT,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
)


@dataclass(frozen=True)
class ConnectorPlaybook:
    id: str
    module: str
    cli_flag: str
    env_keys: tuple[str, ...]
    user_steps: tuple[str, ...]
    smoke_hint: str


PLAYBOOKS: tuple[ConnectorPlaybook, ...] = (
    ConnectorPlaybook(
        id=CONNECTOR_CORPORATE_BADGE,
        module=MODULE_FINANCE,
        cli_flag="--corporate-badge",
        env_keys=(),
        user_steps=(
            "Run apply with --setup-badge",
            "Edit finance_bot/config/badge.yaml: enabled: true",
        ),
        smoke_hint="is_badge_enabled() after badge.yaml",
    ),
    ConnectorPlaybook(
        id=CONNECTOR_BROKER_SYNC,
        module=MODULE_FINANCE,
        cli_flag="--broker-sync",
        env_keys=(),
        user_steps=(
            "cp finance_bot/config/broker_sync.yaml.example → broker_sync.yaml",
            "Set provider: csv (portable) or tinkoff (optional T-Invest API)",
            "csv → broker_balances.csv; tinkoff → TINKOFF_API_TOKEN in .env",
        ),
        smoke_hint="broker_sync.yaml provider not none",
    ),
    ConnectorPlaybook(
        id=CONNECTOR_DOMESTIC_BANK_CARDS,
        module=MODULE_FINANCE,
        cli_flag="--domestic-bank-cards",
        env_keys=(),
        user_steps=(
            "Create card/wallet accounts in finance bot or accounts YAML",
            "Track expenses via NLU in Telegram",
        ),
        smoke_hint="finance module + domestic_bank_cards connector",
    ),
    ConnectorPlaybook(
        id=CONNECTOR_APPLE_HEALTH,
        module=MODULE_PLANNING,
        cli_flag="--apple-health",
        env_keys=(),
        user_steps=(
            "Copy docs/connectors/health/samples/*.txt into your vault health folder",
            "Configure health_parse.yaml aliases if your exporter uses different keys",
            "Optional: iOS/Android Shortcuts or Tasker — docs/connectors/shortcuts/",
        ),
        smoke_hint="health_snapshots / apple_health connector",
    ),
    ConnectorPlaybook(
        id=CONNECTOR_GMAIL_HEALTH,
        module=MODULE_PLANNING,
        cli_flag="--gmail-health-pipeline",
        env_keys=("GMAIL_IMAP_USER", "GMAIL_IMAP_APP_PASSWORD"),
        user_steps=(
            "Gmail → App Password → GMAIL_IMAP_* in .env",
            "iPhone shortcut emails health snapshot; Mac runs iphone_mail_sync on sync",
        ),
        smoke_hint="GMAIL_IMAP_* present",
    ),
    ConnectorPlaybook(
        id=CONNECTOR_APPLE_CALENDAR,
        module=MODULE_PLANNING,
        cli_flag="--apple-calendar",
        env_keys=(),
        user_steps=(
            "Apple shortcut appends Calendar.txt in vault dashboards data folder",
        ),
        smoke_hint="apple_calendar connector",
    ),
    ConnectorPlaybook(
        id=CONNECTOR_MAC_CONTEXT,
        module=MODULE_PLANNING,
        cli_flag="--mac-context",
        env_keys=(),
        user_steps=(
            "Mac shortcut writes focus snapshots under vault actions/Mac/",
        ),
        smoke_hint="mac_context connector",
    ),
    ConnectorPlaybook(
        id=CONNECTOR_KB_SERENDIPITY,
        module=MODULE_KNOWLEDGE,
        cli_flag="--knowledge-serendipity",
        env_keys=(),
        user_steps=("Knowledge module on; serendipity loop starts with unified bot",),
        smoke_hint="knowledge + knowledge_serendipity",
    ),
)

MODULE_PLAYBOOKS: tuple[tuple[str, str, str], ...] = (
    (MODULE_FINANCE, "--finance", "VAULT_PATH, TELEGRAM_UNIFIED_BOT_TOKEN, DEEPSEEK_API_KEY"),
    (MODULE_PLANNING, "--planning", "Same core .env; planning uses unified host"),
    (MODULE_KNOWLEDGE, "--knowledge", "TELEGRAM_USER_ID if ingest from your account"),
)


def playbooks_for_module(module: str) -> list[ConnectorPlaybook]:
    return [p for p in PLAYBOOKS if p.module == module]


def playbook_by_id(connector_id: str) -> Optional[ConnectorPlaybook]:
    for p in PLAYBOOKS:
        if p.id == connector_id:
            return p
    return None
