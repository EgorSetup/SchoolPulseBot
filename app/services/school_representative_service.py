"""
Service for managing SchoolRepresentative profiles.

Handles:
  - Saving school name and class from user input.
  - Retrieving the profile for a given user.
  - Checking whether the profile has all required fields filled.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import SchoolRepresentative, User

logger = logging.getLogger(__name__)


async def get_profile(
    session: AsyncSession, user_id: int
) -> Optional[SchoolRepresentative]:
    """Fetch the SchoolRepresentative profile for a user, or None."""
    result = await session.execute(
        select(SchoolRepresentative).where(SchoolRepresentative.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def has_complete_profile(session: AsyncSession, user_id: int) -> bool:
    """
    Check if the user has a SchoolRepresentative profile with at least
    school_name filled (school_class is optional).
    """
    profile = await get_profile(session, user_id)
    if profile is None:
        return False
    return bool(profile.school_name)


async def save_school(
    session: AsyncSession, user_id: int, school_name: str
) -> SchoolRepresentative:
    """
    Save (or update) the school name for a SchoolRepresentative.

    Returns the profile object.
    """
    profile = await get_profile(session, user_id)

    if profile is None:
        profile = SchoolRepresentative(
            user_id=user_id,
            school_name=school_name.strip(),
        )
        session.add(profile)
        logger.info("Created SchoolRepresentative profile for user_id=%d", user_id)
    else:
        profile.school_name = school_name.strip()
        logger.info("Updated school_name for user_id=%d: %s", user_id, school_name)

    await session.flush()
    return profile


async def save_school_class(
    session: AsyncSession, user_id: int, school_class: str
) -> SchoolRepresentative:
    """
    Save (or update) the class name for a SchoolRepresentative.
    Assumes profile already exists (school_name was set first).
    """
    profile = await get_profile(session, user_id)

    if profile is None:
        raise ValueError(
            f"Cannot set school_class — no SchoolRepresentative profile exists for user_id={user_id}. "
            f"Call save_school() first."
        )

    profile.school_class = school_class.strip()
    logger.info("Updated school_class for user_id=%d: %s", user_id, school_class)
    await session.flush()
    return profile


async def set_notification_preferences(
    session: AsyncSession, user_id: int, preferences: dict
) -> SchoolRepresentative:
    """Store notification preferences as a JSON string."""
    profile = await get_profile(session, user_id)
    if profile is None:
        raise ValueError(f"No profile for user_id={user_id}")

    profile.notification_preferences = json.dumps(preferences, ensure_ascii=False)
    await session.flush()
    return profile


async def get_notification_preferences(
    session: AsyncSession, user_id: int
) -> Optional[dict]:
    """Parse and return notification preferences, or None."""
    profile = await get_profile(session, user_id)
    if profile is None or not profile.notification_preferences:
        return None
    return json.loads(profile.notification_preferences)
