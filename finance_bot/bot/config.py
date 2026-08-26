"""Finance bot settings (env via pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.finance_db_paths import database_url_for_path, resolve_canonical_write_db
from shared.constants import timezone_name


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TELEGRAM_BOT_TOKEN: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_FINANCE_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
        description="Telegram bot token from BotFather",
    )
    TIMEZONE: str = Field(
        default_factory=timezone_name,
        description="Default timezone (TIMEZONE env, default UTC)",
    )
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./finance.db",
        description="SQLAlchemy URL; relative paths resolve under finance_bot root",
    )
    TINKOFF_API_TOKEN: Optional[str] = Field(default=None)
    TINKOFF_IGNORE_ACCOUNT_IDS: Optional[str] = Field(default=None)
    BASE_CURRENCY: str = Field(default="USD")
    DEEPSEEK_API_KEY: Optional[str] = Field(default=None)
    DEEPSEEK_API_TOKEN: Optional[str] = Field(default=None)
    DEEPSEEK_BASE_URL: Optional[str] = Field(default=None)
    DEEPSEEK_MODEL: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def _canonical_database_url(self) -> "Settings":
        canonical = resolve_canonical_write_db(database_url=self.DATABASE_URL)
        object.__setattr__(self, "DATABASE_URL", database_url_for_path(canonical))
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
