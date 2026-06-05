"""
Authorization service — resolves the user's role by their MAX user ID.

Lookup order:
  1. Check if user exists in local DB → return their stored role.
  2. If not found, create a new User with default role (school_representative).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


async def resolve_user_role(
    session: AsyncSession, max_id: int, *, username: str | None = None
) -> tuple[User, bool]:
    """
    Resolve (or create) a user by their MAX platform ID.

    Returns (user, is_new) tuple where is_new indicates the user was just created.
    """
    result = await session.execute(select(User).where(User.max_id == max_id))
    user: Optional[User] = result.scalar_one_or_none()

    if user is not None:
        logger.debug("Found existing user max_id=%d role=%s", max_id, user.role.value)
        return user, False

    # Create new user with default School_Representative role
    user = User(
        max_id=max_id,
        username=username,
        role=UserRole.school_representative,
        is_verified=False,
    )
    session.add(user)
    await session.flush()
    logger.info("Created new user max_id=%d role=school_representative", max_id)
    return user, True


async def get_user_by_id(
    session: AsyncSession, max_id: int
) -> Optional[User]:
    """Fetch a user by their MAX ID, or None if not found."""
    result = await session.execute(select(User).where(User.max_id == max_id))
    return result.scalar_one_or_none()


async def set_user_role(
    session: AsyncSession,
    max_id: int,
    new_role: UserRole,
    *,
    verified: bool | None = None,
) -> Optional[User]:
    """Change a user's role. Optionally update verification status."""
    user = await get_user_by_id(session, max_id)
    if user is None:
        logger.warning("Attempted to set role for unknown user max_id=%d", max_id)
        return None

    user.role = new_role
    if verified is not None:
        user.is_verified = verified

    logger.info("Updated user max_id=%d role=%s verified=%s", max_id, new_role.value, user.is_verified)
    return user
