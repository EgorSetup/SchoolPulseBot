from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.notification import ReadReceipt


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    school_representative = "school_representative"
    organizer = "organizer"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    max_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    """MAX platform user ID — primary key, set by the bot on first interaction."""

    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.school_representative,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    registration_state: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=None,
        comment="Current FSM state for multi-step dialogs (e.g. awaiting_school, awaiting_class)",
    )
    """Persistent dialog state for multi-step registration/event creation flows."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=datetime.utcnow, nullable=True
    )

    # Relationships (strings to avoid circular imports)
    school_rep: Mapped[Optional["SchoolRepresentative"]] = relationship(
        "SchoolRepresentative", back_populates="user", uselist=False
    )
    organizer_profile: Mapped[Optional["Organizer"]] = relationship(
        "Organizer", back_populates="user", uselist=False
    )
    admin_profile: Mapped[Optional["Admin"]] = relationship(
        "Admin", back_populates="user", uselist=False
    )
    read_receipts: Mapped[list["ReadReceipt"]] = relationship(
        "ReadReceipt", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User max_id={self.max_id} role={self.role} verified={self.is_verified}>"


class SchoolRepresentative(Base):
    """Extended profile for School_Representative role."""

    __tablename__ = "school_representatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.max_id"), nullable=False, unique=True
    )
    school_name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_class: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notification_preferences: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="JSON string of notification preferences"
    )

    user: Mapped["User"] = relationship("User", back_populates="school_rep")

    def __repr__(self) -> str:
        return f"<SchoolRepresentative user_id={self.user_id} school={self.school_name}>"


class Organizer(Base):
    """Extended profile for Organizer role."""

    __tablename__ = "organizers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.max_id"), nullable=False, unique=True
    )
    organization: Mapped[str] = mapped_column(String(255), nullable=False)
    created_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="organizer_profile")

    def __repr__(self) -> str:
        return f"<Organizer user_id={self.user_id} org={self.organization}>"


class Admin(Base):
    """Extended profile for Admin role."""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.max_id"), nullable=False, unique=True
    )
    can_verify: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_moderate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="admin_profile")

    def __repr__(self) -> str:
        return f"<Admin user_id={self.user_id} verify={self.can_verify} moderate={self.can_moderate}>"
