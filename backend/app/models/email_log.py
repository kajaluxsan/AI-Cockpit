"""Email log model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmailDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EmailKind(str, Enum):
    APPLICATION = "application"
    FOLLOWUP_REQUEST = "followup_request"
    REPLY = "reply"
    NOTIFICATION = "notification"
    OTHER = "other"


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )

    direction: Mapped[EmailDirection] = mapped_column(
        SAEnum(EmailDirection), default=EmailDirection.INBOUND, index=True
    )
    kind: Mapped[EmailKind] = mapped_column(
        SAEnum(EmailKind), default=EmailKind.APPLICATION, index=True
    )

    message_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    from_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    to_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments_count: Mapped[int] = mapped_column(Integer, default=0)
    answered: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    candidate: Mapped["Candidate | None"] = relationship(  # noqa: F821
        back_populates="email_logs"
    )
