"""
Service for broadcasting notifications to SchoolRepresentatives.

Handles:
  - Selecting recipients (with optional filters by school / class).
  - Creating Notification + NotificationRecipient records in a transaction.
  - Sending messages via MAX API with rate-limit awareness (30 RPS).
  - Recording read receipts (acknowledgements).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.notification import (
    Notification,
    NotificationRecipient,
    ReadReceipt,
)
from app.models.user import SchoolRepresentative, User, UserRole
from app.services.max_api import send_message

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────

MAX_RPS = 30  # MAX API rate limit: 30 requests per second
_INTERVAL = 1.0 / MAX_RPS  # ~0.033s between sends


# ──────────────────────────────────────────────────────
#  Recipient selection
# ──────────────────────────────────────────────────────


async def get_recipients(
    session: AsyncSession,
    *,
    school_name: str | None = None,
    school_class: str | None = None,
) -> list[SchoolRepresentative]:
    """
    Fetch all SchoolRepresentatives matching optional filters.

    Args:
        school_name: If set, only representatives from this school.
        school_class: If set, only representatives of this class (requires school_name too).

    Returns list of SchoolRepresentative records (each has .user_id).
    """
    query = (
        select(SchoolRepresentative)
        .join(User, User.max_id == SchoolRepresentative.user_id)
        .where(User.role == UserRole.school_representative)
        .where(User.is_verified == True)
    )

    if school_name:
        query = query.where(SchoolRepresentative.school_name == school_name)
    if school_class:
        query = query.where(SchoolRepresentative.school_class == school_class)

    result = await session.execute(query)
    return list(result.scalars().all())


# ──────────────────────────────────────────────────────
#  Send broadcast (transactional + rate-limited)
# ──────────────────────────────────────────────────────


async def send_broadcast(
    session: AsyncSession,
    *,
    event_id: int,
    text: str,
    recipient_ids: list[int],
) -> Notification:
    """
    Send a notification to all specified recipients.

    Steps (all in one DB transaction):
      1. Create a Notification record.
      2. Create NotificationRecipient rows (to prevent duplicates).
      3. Send messages via MAX API (rate-limited).
      4. Mark successful sends on NotificationRecipient rows.
      5. On error, record the error_message.

    The caller is responsible for session.commit() after this returns.
    """
    notification = Notification(
        event_id=event_id,
        text=text,
        sent_at=datetime.utcnow(),
    )
    session.add(notification)
    await session.flush()

    # Deduplicate: check if any of these user_ids already have a recipient
    # record for this notification (shouldn't happen, but safe guard).
    existing = await session.execute(
        select(NotificationRecipient.user_id).where(
            and_(
                NotificationRecipient.notification_id == notification.id,
                NotificationRecipient.user_id.in_(recipient_ids),
            )
        )
    )
    existing_ids = set(existing.scalars().all())
    new_ids = [uid for uid in recipient_ids if uid not in existing_ids]

    # Create recipient records
    recipients: list[NotificationRecipient] = []
    for user_id in new_ids:
        recipient = NotificationRecipient(
            notification_id=notification.id,
            user_id=user_id,
            sent=False,
        )
        session.add(recipient)
        recipients.append(recipient)
    await session.flush()

    logger.info(
        "Broadcast prepared: notification_id=%d, recipients=%d (skipped %d duplicates)",
        notification.id,
        len(recipients),
        len(recipient_ids) - len(new_ids),
    )

    # ── Send messages with rate limiting ──
    sent_count = 0
    error_count = 0

    for recipient in recipients:
        try:
            await send_message(
                text,
                user_id=recipient.user_id,
            )
            recipient.sent = True
            recipient.sent_at = datetime.utcnow()
            sent_count += 1

        except Exception as exc:
            logger.warning(
                "Failed to send notification_id=%d to user_id=%d: %s",
                notification.id,
                recipient.user_id,
                exc,
            )
            recipient.error_message = str(exc)[:500]
            error_count += 1

        # Rate limit: sleep between sends
        await asyncio.sleep(_INTERVAL)

    logger.info(
        "Broadcast done: notification_id=%d, sent=%d, errors=%d",
        notification.id,
        sent_count,
        error_count,
    )

    # Flush status updates to the DB (caller will commit)
    await session.flush()
    return notification


# ──────────────────────────────────────────────────────
#  Read receipts
# ──────────────────────────────────────────────────────


async def record_read_receipt(
    session: AsyncSession,
    *,
    user_id: int,
    notification_id: int,
) -> bool:
    """
    Record that a user has read/acknowledged a notification.

    Returns True if the receipt was newly created, False if it already existed.
    """
    # Check for duplicate
    existing = await session.execute(
        select(ReadReceipt).where(
            and_(
                ReadReceipt.user_id == user_id,
                ReadReceipt.notification_id == notification_id,
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        logger.debug(
            "Duplicate read receipt: user_id=%d notification_id=%d",
            user_id,
            notification_id,
        )
        return False

    receipt = ReadReceipt(
        user_id=user_id,
        notification_id=notification_id,
        read_at=datetime.utcnow(),
    )
    session.add(receipt)
    await session.flush()

    logger.info(
        "Read receipt recorded: user_id=%d notification_id=%d",
        user_id,
        notification_id,
    )
    return True


async def get_last_notification_for_user(
    session: AsyncSession,
    user_id: int,
) -> Optional[Notification]:
    """
    Get the most recent notification sent to a specific user.
    Used to attach the notification_id in callback_data.
    """
    result = await session.execute(
        select(NotificationRecipient)
        .where(NotificationRecipient.user_id == user_id)
        .where(NotificationRecipient.sent == True)
        .order_by(NotificationRecipient.sent_at.desc())
        .limit(1)
        .options(selectinload(NotificationRecipient.notification))
    )
    recipient = result.scalar_one_or_none()
    if recipient is None:
        return None
    return recipient.notification
