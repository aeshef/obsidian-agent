"""Vault audit report (tags + optional maintainer duplicates scripts)."""

from knowledge_bot.services.vault_audit.report import build_vault_audit_report, write_vault_audit_report

__all__ = ["build_vault_audit_report", "write_vault_audit_report"]
