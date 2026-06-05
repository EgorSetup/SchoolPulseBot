from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.user import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    event: Mapped["Event"] = relationship("Event", back_populates="notifications")
    read_receipts: Mapped[list["ReadReceipt"]] = relationship(
        "ReadReceipt", back_populates="notification", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} event_id={self.event_id}>"


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

    user: Mapped["User"] = relationship("User", back_populates="read_receipts")
    notification: Mapped["Notification"] = relationship(
        "Notification", back_populates="read_receipts"
    )

    def __repr__(self) -> str:
        return f"<ReadReceipt user_id={self.user_id} notification_id={self.notification_id}>"
