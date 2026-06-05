"""
Admin log model — tracks all actions performed by Admin users.

Stored in a separate admin_logs table for audit purposes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


class AdminLog(Base):
    """Immutable audit log entry for admin actions."""

    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    """MAX ID of the admin who performed the action."""

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    """Short action name, e.g. 'verify_user', 'reject_user', 'set_role'."""

    target_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    """Target user ID or entity ID the action was performed on."""

    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    """JSON or human-readable details about the action."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<AdminLog id={self.id} admin_id={self.admin_id} "
            f"action={self.action!r} target={self.target_id}>"
        )
