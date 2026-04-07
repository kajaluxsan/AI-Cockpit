"""Candidate Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.candidate import CandidateSource, CandidateStatus


class CandidateBase(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    location: str | None = None
    language: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[str] | None = None
    experience_years: float | None = None
    education: list[dict[str, Any]] | None = None
    work_history: list[dict[str, Any]] | None = None
    salary_expectation: int | None = None
    salary_currency: str | None = None
    availability: str | None = None
    languages_spoken: list[str] | None = None
    notes: str | None = None


class CandidateCreate(CandidateBase):
    source: CandidateSource = CandidateSource.MANUAL
    source_reference: str | None = None
    cv_text: str | None = None


class CandidateUpdate(CandidateBase):
    status: CandidateStatus | None = None


class CandidateOut(CandidateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: CandidateSource
    source_reference: str | None = None
    status: CandidateStatus
    missing_fields: list[str] | None = None
    created_at: datetime
    updated_at: datetime
