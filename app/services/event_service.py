"""
Service for managing events (CRUD) by Organizer users
and event registration by SchoolRepresentative users.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventRegistration
from app.models.user import Organizer, User

logger = logging.getLogger(__name__)


async def create_event(
    session: AsyncSession,
    *,
    organizer_id: int,
    title: str,
    description: Optional[str],
    scheduled_at: datetime,
    school_name: Optional[str] = None,
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
        school_name=school_name,
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
        "Event created: id=%d title=%r organizer_id=%d school_name=%s",
        event.id,
        event.title,
        organizer_id,
        school_name,
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


async def get_events_by_school(
    session: AsyncSession,
    school_name: str,
    *,
    only_future: bool = True,
) -> list[Event]:
    """
    Get all events for a given school name, optionally only future events.
    Ordered by scheduled_at ascending (soonest first).
    """
    conditions = [Event.school_name == school_name]
    if only_future:
        conditions.append(Event.scheduled_at >= datetime.utcnow())

    result = await session.execute(
        select(Event)
        .where(and_(*conditions))
        .order_by(Event.scheduled_at.asc())
    )
    return list(result.scalars().all())


async def register_for_event(
    session: AsyncSession,
    *,
    user_id: int,
    event_id: int,
) -> EventRegistration:
    """
    Register a user for an event. Returns the created registration.
    Raises ValueError if the user is already registered.
    """
    # Check for duplicate
    existing = await session.execute(
        select(EventRegistration).where(
            and_(
                EventRegistration.user_id == user_id,
                EventRegistration.event_id == event_id,
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("User is already registered for this event")

    registration = EventRegistration(
        user_id=user_id,
        event_id=event_id,
    )
    session.add(registration)
    await session.flush()

    logger.info(
        "User %d registered for event %d (registration_id=%d)",
        user_id, event_id, registration.id,
    )
    return registration


async def is_user_registered(
    session: AsyncSession,
    *,
    user_id: int,
    event_id: int,
) -> bool:
    """Check if a user is already registered for an event."""
    result = await session.execute(
        select(EventRegistration).where(
            and_(
                EventRegistration.user_id == user_id,
                EventRegistration.event_id == event_id,
            )
        )
    )
    return result.scalar_one_or_none() is not None


async def get_user_registrations(
    session: AsyncSession,
    user_id: int,
) -> list[EventRegistration]:
    """Get all registrations for a given user."""
    result = await session.execute(
        select(EventRegistration)
        .where(EventRegistration.user_id == user_id)
        .order_by(EventRegistration.registered_at.desc())
    )
    return list(result.scalars().all())
