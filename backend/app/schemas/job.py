"""Job Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.job import JobSource, JobStatus


class JobBase(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    description: str | None = None
    required_skills: list[str] | None = None
    nice_to_have_skills: list[str] | None = None
    min_experience_years: float | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    employment_type: str | None = None
    languages_required: list[str] | None = None


class JobCreate(JobBase):
    source: JobSource = JobSource.MANUAL
    source_reference: str | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    required_skills: list[str] | None = None
    nice_to_have_skills: list[str] | None = None
    min_experience_years: float | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    employment_type: str | None = None
    languages_required: list[str] | None = None
    status: JobStatus | None = None


class JobOut(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: JobSource
    source_reference: str | None = None
    status: JobStatus
    created_at: datetime
    updated_at: datetime
