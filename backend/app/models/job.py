"""Job (open position) model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(str, Enum):
    OPEN = "open"
    PAUSED = "paused"
    FILLED = "filled"
    CLOSED = "closed"


class JobSource(str, Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    EXTERNAL_API = "external_api"
    MANUAL = "manual"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    required_skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    nice_to_have_skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    min_experience_years: Mapped[float | None] = mapped_column(nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    languages_required: Mapped[list | None] = mapped_column(JSON, nullable=True)

    source: Mapped[JobSource] = mapped_column(SAEnum(JobSource), default=JobSource.MANUAL)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus), default=JobStatus.OPEN, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    matches: Mapped[list["Match"]] = relationship(  # noqa: F821
        back_populates="job", cascade="all, delete-orphan"
    )
