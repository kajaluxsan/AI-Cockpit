"""Candidate (CRM profile) model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CandidateStatus(str, Enum):
    NEW = "new"
    PARSED = "parsed"
    INFO_REQUESTED = "info_requested"
    MATCHED = "matched"
    CONTACTED = "contacted"
    INTERVIEW = "interview"
    PLACED = "placed"
    REJECTED = "rejected"


class CandidateSource(str, Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    EXTERNAL_API = "external_api"
    MANUAL = "manual"


class Candidate(Base):
    """CRM profile for a candidate.

    A candidate is identified primarily by email address. When a new CV or
    message is received, :func:`app.services.crm.upsert_candidate_from_parse`
    checks whether a profile with the same email already exists and updates it
    in place — so the protocol (email / call / chat history) remains attached
    to a single profile over time.
    """

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identity (first_name, last_name, email, phone required by the CRM layer)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)  # de | en
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Profile
    headline: Mapped[str | None] = mapped_column(String(300), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    experience_years: Mapped[float | None] = mapped_column(nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    work_history: Mapped[list | None] = mapped_column(JSON, nullable=True)
    salary_expectation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    availability: Mapped[str | None] = mapped_column(String(100), nullable=True)
    languages_spoken: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Source
    source: Mapped[CandidateSource] = mapped_column(
        SAEnum(CandidateSource), default=CandidateSource.EMAIL
    )
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cv_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_attachment_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cv_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Status
    status: Mapped[CandidateStatus] = mapped_column(
        SAEnum(CandidateStatus), default=CandidateStatus.NEW, index=True
    )
    missing_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    matches: Mapped[list["Match"]] = relationship(  # noqa: F821
        back_populates="candidate", cascade="all, delete-orphan"
    )
    call_logs: Mapped[list["CallLog"]] = relationship(  # noqa: F821
        back_populates="candidate", cascade="all, delete-orphan"
    )
    email_logs: Mapped[list["EmailLog"]] = relationship(  # noqa: F821
        back_populates="candidate", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list["ChatMessage"]] = relationship(  # noqa: F821
        back_populates="candidate", cascade="all, delete-orphan"
    )
