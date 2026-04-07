"""Voice call log model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
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


class CallStatus(str, Enum):
    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    CANCELED = "canceled"


class CallDirection(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    match_id: Mapped[int | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL"), nullable=True
    )

    twilio_call_sid: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    direction: Mapped[CallDirection] = mapped_column(
        SAEnum(CallDirection), default=CallDirection.OUTBOUND
    )
    from_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[CallStatus] = mapped_column(
        SAEnum(CallStatus), default=CallStatus.INITIATED, index=True
    )

    detected_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_segments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    interest_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    candidate: Mapped["Candidate | None"] = relationship(  # noqa: F821
        back_populates="call_logs"
    )
