"""Match Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.match import MatchStatus


class MatchBase(BaseModel):
    candidate_id: int
    job_id: int
    score: float = 0.0
    score_breakdown: dict[str, Any] | None = None
    rationale: str | None = None


class MatchCreate(MatchBase):
    pass


class MatchUpdate(BaseModel):
    status: MatchStatus | None = None
    rationale: str | None = None


class MatchOut(MatchBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: MatchStatus
    created_at: datetime
    updated_at: datetime
