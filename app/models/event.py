from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.user import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.notification import Notification


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    organizer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.max_id"), nullable=False
    )
    school_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="School name this event belongs to (matches school_representatives.school_name)",
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    organizer: Mapped["User"] = relationship("User", backref="events")
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="event", cascade="all, delete-orphan"
    )

    registrations: Mapped[list["EventRegistration"]] = relationship(
        "EventRegistration", back_populates="event", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title!r}>"


class EventRegistration(Base):
    """Tracks which users have registered for which events."""

    __tablename__ = "event_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.max_id"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id"), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    event: Mapped["Event"] = relationship("Event", back_populates="registrations")

    def __repr__(self) -> str:
        return (
            f"<EventRegistration user_id={self.user_id} "
            f"event_id={self.event_id}>"
        )
