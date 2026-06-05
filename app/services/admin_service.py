"""
Admin service — business logic for the admin panel.

Provides:
  - Verification queue (unverified users)
  - User management (assign roles)
  - Global system dashboard (stats)
  - Admin action logging
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_log import AdminLog
from app.models.event import Event
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────
#  Data classes
# ──────────────────────────────────────────────────────


@dataclass
class SystemDashboard:
    """Global system statistics for the admin dashboard."""

    total_users: int = 0
    total_verified_users: int = 0
    total_active_schools: int = 0
    total_events: int = 0
    events_this_week: int = 0
    total_organizers: int = 0
    total_admins: int = 0


# ──────────────────────────────────────────────────────
#  Verification queue
# ──────────────────────────────────────────────────────


async def get_verification_queue(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[User], int]:
    """
    Get paginated list of unverified users (is_verified = False).

    Returns (users, total_count).
    """
    # Count total
    count_result = await session.execute(
        select(func.count(User.max_id)).where(User.is_verified == False)
    )
    total = count_result.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    result = await session.execute(
        select(User)
        .where(User.is_verified == False)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    users = list(result.scalars().all())
    return users, total


async def verify_user(
    session: AsyncSession,
    admin_id: int,
    target_max_id: int,
) -> Optional[User]:
    """Approve a user's verification."""
    user = await session.get(User, target_max_id)
    if user is None:
        logger.warning("Admin %d tried to verify nonexistent user %d", admin_id, target_max_id)
        return None

    user.is_verified = True
    await session.flush()

    await _log_action(
        session,
        admin_id=admin_id,
        action="verify_user",
        target_id=str(target_max_id),
        details=f"Verified user max_id={target_max_id}, role={user.role.value}",
    )

    logger.info("Admin %d verified user %d", admin_id, target_max_id)
    return user


async def reject_user(
    session: AsyncSession,
    admin_id: int,
    target_max_id: int,
) -> bool:
    """Reject / delete an unverified user from the system."""
    user = await session.get(User, target_max_id)
    if user is None:
        logger.warning("Admin %d tried to reject nonexistent user %d", admin_id, target_max_id)
        return False

    # Log before deleting so we have the record
    await _log_action(
        session,
        admin_id=admin_id,
        action="reject_user",
        target_id=str(target_max_id),
        details=f"Rejected and removed user max_id={target_max_id}, role={user.role.value}",
    )

    await session.delete(user)
    await session.flush()

    logger.info("Admin %d rejected (deleted) user %d", admin_id, target_max_id)
    return True


# ──────────────────────────────────────────────────────
#  User management — role assignment
# ──────────────────────────────────────────────────────


async def search_users(
    session: AsyncSession,
    *,
    query: str = "",
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[User], int]:
    """
    Search users by ID (exact) or by username (partial match).
    Returns (users, total_count).

    The query can be:
      - A numeric string → search by max_id
      - A text string → search by username (ILIKE)
      - Empty → return all users
    """
    base_query = select(User)

    if query:
        if query.isdigit():
            # Exact ID match
            base_query = base_query.where(User.max_id == int(query))
        else:
            # Username partial match (case-insensitive)
            base_query = base_query.where(User.username.ilike(f"%{query}%"))

    # Count total
    count_result = await session.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    result = await session.execute(
        base_query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = list(result.scalars().all())
    return users, total


async def set_user_role(
    session: AsyncSession,
    admin_id: int,
    target_max_id: int,
    new_role: UserRole,
    *,
    verified: Optional[bool] = None,
) -> Optional[User]:
    """
    Change a user's role. Admin-only operation.

    Args:
        new_role: The role to assign.
        verified: Optionally force a verification status change.

    Returns the updated User, or None if not found.
    """
    user = await session.get(User, target_max_id)
    if user is None:
        logger.warning("Admin %d tried to set role for unknown user %d", admin_id, target_max_id)
        return None

    old_role = user.role
    user.role = new_role
    if verified is not None:
        user.is_verified = verified

    await session.flush()

    await _log_action(
        session,
        admin_id=admin_id,
        action="set_role",
        target_id=str(target_max_id),
        details=json.dumps(
            {
                "old_role": old_role.value,
                "new_role": new_role.value,
                "verified": user.is_verified,
            },
            ensure_ascii=False,
        ),
    )

    logger.info(
        "Admin %d changed role of user %d: %s -> %s",
        admin_id, target_max_id, old_role.value, new_role.value,
    )
    return user


# ──────────────────────────────────────────────────────
#  System dashboard
# ──────────────────────────────────────────────────────


async def get_system_dashboard(session: AsyncSession) -> SystemDashboard:
    """Collect global system statistics."""
    # Total users
    total_users_result = await session.execute(select(func.count(User.max_id)))
    total_users = total_users_result.scalar() or 0

    # Verified users
    verified_result = await session.execute(
        select(func.count(User.max_id)).where(User.is_verified == True)
    )
    total_verified = verified_result.scalar() or 0

    # Count of each role
    organizer_result = await session.execute(
        select(func.count(User.max_id)).where(User.role == UserRole.organizer)
    )
    total_organizers = organizer_result.scalar() or 0

    admin_result = await session.execute(
        select(func.count(User.max_id)).where(User.role == UserRole.admin)
    )
    total_admins = admin_result.scalar() or 0

    # Total events
    events_result = await session.execute(select(func.count(Event.id)))
    total_events = events_result.scalar() or 0

    # Events created this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_events_result = await session.execute(
        select(func.count(Event.id)).where(Event.created_at >= week_ago)
    )
    events_this_week = week_events_result.scalar() or 0

    # Active schools (distinct school names from SchoolRepresentative)
    from app.models.user import SchoolRepresentative

    schools_result = await session.execute(
        select(func.count(func.distinct(SchoolRepresentative.school_name)))
    )
    total_active_schools = schools_result.scalar() or 0

    return SystemDashboard(
        total_users=total_users,
        total_verified_users=total_verified,
        total_active_schools=total_active_schools,
        total_events=total_events,
        events_this_week=events_this_week,
        total_organizers=total_organizers,
        total_admins=total_admins,
    )


# ──────────────────────────────────────────────────────
#  Admin logs
# ──────────────────────────────────────────────────────


async def get_admin_logs(
    session: AsyncSession,
    *,
    limit: int = 20,
) -> list[AdminLog]:
    """Get the most recent admin log entries."""
    result = await session.execute(
        select(AdminLog)
        .order_by(AdminLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ──────────────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────────────


async def _log_action(
    session: AsyncSession,
    *,
    admin_id: int,
    action: str,
    target_id: Optional[str] = None,
    details: Optional[str] = None,
) -> AdminLog:
    """Record an admin action in the log."""
    log_entry = AdminLog(
        admin_id=admin_id,
        action=action,
        target_id=target_id,
        details=details,
        created_at=datetime.utcnow(),
    )
    session.add(log_entry)
    await session.flush()

    # Also log to console
    logger.info(
        "ADMIN ACTION [admin=%d] %s target=%s details=%s",
        admin_id, action, target_id, details or "",
    )
    return log_entry
