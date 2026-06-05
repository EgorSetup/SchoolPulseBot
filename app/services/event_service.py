"""
Service for managing events (CRUD) by Organizer users.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.user import Organizer, User

logger = logging.getLogger(__name__)


async def create_event(
    session: AsyncSession,
    *,
    organizer_id: int,
    title: str,
    description: Optional[str],
    scheduled_at: datetime,
) -> Event:
    """
    Create a new event and bind it to the organizer.

    Also increments the organizer's created_events_count.
    Uses a single transaction (caller commits).
    """
    event = Event(
        title=title.strip(),
        description=description.strip() if description else None,
        organizer_id=organizer_id,
        scheduled_at=scheduled_at,
    )
    session.add(event)
    await session.flush()

    # Update the organizer's event counter
    result = await session.execute(
        select(Organizer).where(Organizer.user_id == organizer_id)
    )
    organizer = result.scalar_one_or_none()
    if organizer is not None:
        organizer.created_events_count += 1

    logger.info(
        "Event created: id=%d title=%r organizer_id=%d",
        event.id,
        event.title,
        organizer_id,
    )
    return event


async def get_event_by_id(
    session: AsyncSession, event_id: int
) -> Optional[Event]:
    """Fetch a single event by its ID."""
    result = await session.execute(select(Event).where(Event.id == event_id))
    return result.scalar_one_or_none()


async def get_organizer_events(
    session: AsyncSession, organizer_id: int
) -> list[Event]:
    """Get all events for a given organizer, newest first."""
    result = await session.execute(
        select(Event)
        .where(Event.organizer_id == organizer_id)
        .order_by(Event.created_at.desc())
    )
    return list(result.scalars().all())


async def get_organizer_profile(
    session: AsyncSession, user_id: int
) -> Optional[Organizer]:
    """Fetch the Organizer profile for a user."""
    result = await session.execute(
        select(Organizer).where(Organizer.user_id == user_id)
    )
    return result.scalar_one_or_none()
