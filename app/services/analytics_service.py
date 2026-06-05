"""
Analytics service for Organizer dashboard.

Provides summary statistics:
  - Total notifications sent
  - Total read receipts (acknowledgements)
  - Conversion rate (reads / sends)
  - Per-event breakdown
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.notification import Notification, NotificationRecipient, ReadReceipt
from app.models.event import Event

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsOverview:
    """Aggregated analytics data for a given organizer."""

    total_sent: int = 0
    total_read: int = 0
    conversion_rate: float = 0.0
    event_count: int = 0


@dataclass
class EventAnalytics:
    """Per-event analytics."""

    event_id: int
    event_title: str
    sent_count: int = 0
    read_count: int = 0
    conversion_rate: float = 0.0


async def get_analytics_overview(
    session: AsyncSession,
    organizer_id: int,
) -> AnalyticsOverview:
    """
    Get aggregated analytics for an organizer.

    Counts all notifications across all events owned by this organizer.
    """
    # Get all event IDs for this organizer
    events_result = await session.execute(
        select(Event.id).where(Event.organizer_id == organizer_id)
    )
    event_ids = [row[0] for row in events_result.all()]
    event_count = len(event_ids)

    if not event_ids:
        return AnalyticsOverview(event_count=0)

    # Total sent notifications (count of NotificationRecipient records
    # linked to notifications of these events)
    sent_result = await session.execute(
        select(func.count(NotificationRecipient.id))
        .select_from(NotificationRecipient)
        .join(Notification, Notification.id == NotificationRecipient.notification_id)
        .where(Notification.event_id.in_(event_ids))
        .where(NotificationRecipient.sent == True)
    )
    total_sent = sent_result.scalar() or 0

    # Total read receipts (count of ReadReceipt records linked to
    # notifications of these events)
    read_result = await session.execute(
        select(func.count(ReadReceipt.id))
        .select_from(ReadReceipt)
        .join(Notification, Notification.id == ReadReceipt.notification_id)
        .where(Notification.event_id.in_(event_ids))
    )
    total_read = read_result.scalar() or 0

    conversion_rate = (total_read / total_sent * 100) if total_sent > 0 else 0.0

    return AnalyticsOverview(
        total_sent=total_sent,
        total_read=total_read,
        conversion_rate=round(conversion_rate, 1),
        event_count=event_count,
    )


async def get_event_analytics_list(
    session: AsyncSession,
    organizer_id: int,
) -> list[EventAnalytics]:
    """
    Get per-event analytics for all events owned by this organizer.
    """
    # Fetch all events for this organizer with their notifications loaded
    events_result = await session.execute(
        select(Event)
        .where(Event.organizer_id == organizer_id)
        .order_by(Event.created_at.desc())
        .options(selectinload(Event.notifications))
    )
    events: list[Event] = list(events_result.scalars().all())

    result: list[EventAnalytics] = []
    for event in events:
        notification_ids = [n.id for n in event.notifications]
        if not notification_ids:
            result.append(
                EventAnalytics(
                    event_id=event.id,
                    event_title=event.title,
                    sent_count=0,
                    read_count=0,
                    conversion_rate=0.0,
                )
            )
            continue

        # Count sent
        sent_result = await session.execute(
            select(func.count(NotificationRecipient.id))
            .where(NotificationRecipient.notification_id.in_(notification_ids))
            .where(NotificationRecipient.sent == True)
        )
        sent_count = sent_result.scalar() or 0

        # Count read
        read_result = await session.execute(
            select(func.count(ReadReceipt.id))
            .where(ReadReceipt.notification_id.in_(notification_ids))
        )
        read_count = read_result.scalar() or 0

        conversion_rate = (read_count / sent_count * 100) if sent_count > 0 else 0.0

        result.append(
            EventAnalytics(
                event_id=event.id,
                event_title=event.title,
                sent_count=sent_count,
                read_count=read_count,
                conversion_rate=round(conversion_rate, 1),
            )
        )

    return result
