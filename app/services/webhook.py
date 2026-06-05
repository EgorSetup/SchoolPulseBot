"""
Webhook subscription management — subscribe/unsubscribe from MAX events.
"""

from __future__ import annotations

import logging

from app.config import config
from app.services.max_api import set_webhook_subscription, delete_webhook_subscription

logger = logging.getLogger(__name__)

# Event types relevant to SchoolPulseBot
SUBSCRIPTION_EVENTS: list[str] = [
    "bot_started",
    "bot_added",
    "message_created",
    "message_edited",
    "message_callback",
    "dialog_removed",
    "user_added",
    "user_removed",
]


async def activate_webhook() -> dict[str, bool | str]:
    """
    Subscribe to MAX events via webhook using the configured URL and secret.
    Returns success status.
    """
    if not config.webhook_url.startswith("https://"):
        logger.error("Webhook URL must use HTTPS: %s", config.webhook_url)
        return {"success": False, "message": "Webhook URL must use HTTPS"}

    try:
        result = await set_webhook_subscription(
            url=config.webhook_url,
            update_types=SUBSCRIPTION_EVENTS,
            secret=config.webhook_secret,
        )
        logger.info("Webhook subscription activated: %s", result)
        return {"success": True, "message": "Webhook subscribed successfully"}
    except Exception as exc:
        logger.exception("Failed to activate webhook: %s", exc)
        return {"success": False, "message": str(exc)}


async def deactivate_webhook() -> dict[str, bool | str]:
    """Unsubscribe from all webhook events."""
    try:
        await delete_webhook_subscription()
        logger.info("Webhook subscription deactivated")
        return {"success": True, "message": "Webhook unsubscribed"}
    except Exception as exc:
        logger.exception("Failed to deactivate webhook: %s", exc)
        return {"success": False, "message": str(exc)}
