"""AI chat message history (recruiter ↔ Claude, scoped to one candidate)."""

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


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class ChatMessage(Base):
    """A single message in the per-candidate AI chat.

    The chat is scoped to a candidate: the LLM system prompt includes the
    candidate CV + the protocol (emails/calls) so the recruiter can ask
    questions, request summaries, or trigger actions like "send a follow-up
    mail asking about salary expectation".
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[ChatRole] = mapped_column(SAEnum(ChatRole), default=ChatRole.USER)
    content: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    candidate: Mapped["Candidate"] = relationship(  # noqa: F821
        back_populates="chat_messages"
    )
