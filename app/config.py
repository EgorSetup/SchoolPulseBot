import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # MAX API
    max_token: str = field(default_factory=lambda: os.environ["MAX_BOT_TOKEN"])
    max_api_base: str = "https://platform-api.max.ru"

    # Webhook
    webhook_url: str = field(
        default_factory=lambda: os.environ.get(
            "WEBHOOK_URL", "https://your-domain.com/webhook"
        )
    )
    webhook_secret: str = field(
        default_factory=lambda: os.environ.get("WEBHOOK_SECRET", "")
    )

    # Database
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/school_pulse_bot"
        )
    )

    # Server
    host: str = field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = field(
        default_factory=lambda: int(os.environ.get("PORT", "8000"))
    )

    # Logging
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


config = Config()
