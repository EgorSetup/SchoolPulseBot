from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.user import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class Notification(Base):
    """A notification sent out to recipients about an event."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="notifications")
    recipients: Mapped[list["NotificationRecipient"]] = relationship(
        "NotificationRecipient",
        back_populates="notification",
        cascade="all, delete-orphan",
    )
    read_receipts: Mapped[list["ReadReceipt"]] = relationship(
        "ReadReceipt", back_populates="notification", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} event_id={self.event_id}>"


class NotificationRecipient(Base):
    """
    Tracks which users received a notification and the send status.
    Prevents duplicate sends and provides per-recipient send confirmation.
    """

    __tablename__ = "notification_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notifications.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.max_id"), nullable=False
    )
    sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    notification: Mapped["Notification"] = relationship(
        "Notification", back_populates="recipients"
    )
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<NotificationRecipient notif_id={self.notification_id} "
            f"user_id={self.user_id} sent={self.sent}>"
        )


class ReadReceipt(Base):
    """Tracks which users have read a notification."""

    __tablename__ = "read_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.max_id"), nullable=False
    )
    notification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notifications.id"), nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="read_receipts")
    notification: Mapped["Notification"] = relationship(
        "Notification", back_populates="read_receipts"
    )

    def __repr__(self) -> str:
        return (
            f"<ReadReceipt user_id={self.user_id} "
            f"notification_id={self.notification_id}>"
        )
