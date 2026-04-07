"""Call log Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.call_log import CallDirection, CallStatus


class InitiateCallRequest(BaseModel):
    candidate_id: int
    match_id: int | None = None
    to_number: str | None = None
    language: str | None = None  # de | en | None for auto detect


class CallLogCreate(BaseModel):
    candidate_id: int | None = None
    match_id: int | None = None
    twilio_call_sid: str | None = None
    direction: CallDirection = CallDirection.OUTBOUND
    from_number: str | None = None
    to_number: str | None = None
    status: CallStatus = CallStatus.INITIATED


class CallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int | None
    match_id: int | None
    twilio_call_sid: str | None
    direction: CallDirection
    from_number: str | None
    to_number: str | None
    status: CallStatus
    detected_language: str | None
    duration_seconds: int | None
    transcript: str | None
    transcript_segments: list[Any] | None
    summary: str | None
    interest_level: str | None
    next_steps: str | None
    recording_url: str | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
