"""Email log API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.email_log import EmailDirection, EmailKind, EmailLog

router = APIRouter()


class EmailLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int | None
    direction: EmailDirection
    kind: EmailKind
    message_id: str | None
    from_address: str | None
    to_address: str | None
    subject: str | None
    body: str | None
    attachments_count: int
    answered: bool
    created_at: datetime


@router.get("/", response_model=list[EmailLogOut])
async def list_emails(
    db: AsyncSession = Depends(get_db),
    candidate_id: int | None = None,
    direction: EmailDirection | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> Any:
    query = select(EmailLog).order_by(EmailLog.created_at.desc())
    if candidate_id:
        query = query.where(EmailLog.candidate_id == candidate_id)
    if direction:
        query = query.where(EmailLog.direction == direction)
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
