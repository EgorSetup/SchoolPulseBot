"""Application configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MAX API
    max_bot_token: str = ""
    max_api_base: str = "https://platform-api.max.ru"

    # Webhook
    webhook_url: str = "https://your-domain.com/webhook"
    webhook_secret: str = ""

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/school_pulse_bot"
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Logging
    log_level: str = "INFO"


config = Config()
