"""Candidate Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.candidate import CandidateSource, CandidateStatus


class CandidateBase(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    location: str | None = None
    language: str | None = None
    photo_url: str | None = None
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
    cv_filename: str | None = None
    has_cv: bool = False
    has_photo: bool = False
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_candidate(cls, c: Any) -> "CandidateOut":
        """Serialise a SQLAlchemy Candidate, computing convenience flags.

        ``photo_url`` is rewritten to the API endpoint that streams the actual
        photo, so the frontend never has to know the on-disk storage path.
        """
        photo_url = f"/api/candidates/{c.id}/photo" if c.photo_url else None
        payload = {
            "id": c.id,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "full_name": c.full_name,
            "email": c.email,
            "phone": c.phone,
            "address": c.address,
            "location": c.location,
            "language": c.language,
            "photo_url": photo_url,
            "headline": c.headline,
            "summary": c.summary,
            "skills": c.skills,
            "experience_years": c.experience_years,
            "education": c.education,
            "work_history": c.work_history,
            "salary_expectation": c.salary_expectation,
            "salary_currency": c.salary_currency,
            "availability": c.availability,
            "languages_spoken": c.languages_spoken,
            "notes": c.notes,
            "source": c.source,
            "source_reference": c.source_reference,
            "status": c.status,
            "missing_fields": c.missing_fields,
            "cv_filename": c.cv_filename,
            "has_cv": bool(c.cv_attachment_path),
            "has_photo": bool(c.photo_url),
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        return cls.model_validate(payload)


class ProtocolEntry(BaseModel):
    """Unified protocol / timeline entry (email, call, chat, note)."""

    kind: str  # email_inbound | email_outbound | call | chat | note
    title: str
    body: str | None = None
    status: str | None = None
    direction: str | None = None
    created_at: datetime
    reference_id: int | None = None
