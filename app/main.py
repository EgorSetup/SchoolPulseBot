"""
SchoolPulse Bot — main application entry point.

Starts a FastAPI server that:
  1. Serves the webhook endpoint at POST /webhook
  2. Optionally runs a long-polling loop (dev only)
  3. Provides CLI commands for webhook subscription management
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import config
from app.routers.webhook import router as webhook_router, process_update
from app.services.webhook import activate_webhook

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup / shutdown logic."""
    logger.info("SchoolPulseBot starting up...")
    logger.info("MAX API base: %s", config.max_api_base)
    logger.info("Webhook URL:  %s", config.webhook_url)
    yield
    logger.info("SchoolPulseBot shutting down...")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="SchoolPulse Bot",
        description="MAX chat-bot for managing school events and notifications.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(webhook_router)

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()


# ---- Long Polling (dev only) ---- #

async def run_long_polling():
    """
    Development-only long-polling loop.
    Not recommended for production (MAX limits polling rate and event storage).
    """
    from app.services.max_api import get_updates
    from db.database import db

    logger.warning("Starting long-polling loop (dev mode only)")

    last_event_id: int | None = None
    while True:
        try:
            updates = await get_updates(last_event_id=last_event_id)
            for update in updates:
                event_id = update.get("event_id")
                if event_id is not None:
                    last_event_id = max(
                        last_event_id or 0, int(event_id)
                    )

                async with db.session_factory() as session:
                    await process_update(update, session)
                    await session.commit()

        except Exception:
            logger.exception("Long-polling error, retrying in 5s...")
            await asyncio.sleep(5)
            continue

        await asyncio.sleep(1)


# ---- CLI entry point ---- #

def main():
    """Run the application."""
    import sys

    if "--long-polling" in sys.argv:
        asyncio.run(run_long_polling())
    elif "--subscribe" in sys.argv:
        result = asyncio.run(activate_webhook())
        print(result)
    else:
        uvicorn.run(
            "app.main:app",
            host=config.host,
            port=config.port,
            log_level=config.log_level.lower(),
        )


if __name__ == "__main__":
    main()
