"""Unified messages tab API.

This endpoint powers the "new messages" tab of the cockpit: it returns
recent inbound messages (from the email poller OR from external webhook
ingestion) joined with the candidate profile so the recruiter sees who wrote
and from which CV it maps.

It also exposes two write endpoints:
- ``POST /inbound``    — webhook for the external webapp to push a message.
- ``POST /{id}/read``  — mark a message as acknowledged.
"""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.candidate import Candidate, CandidateSource
from app.models.email_log import EmailDirection, EmailKind, EmailLog
from app.services import crm

router = APIRouter()


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int | None
    candidate_name: str | None
    candidate_photo_url: str | None
    direction: EmailDirection
    kind: EmailKind
    from_address: str | None
    to_address: str | None
    subject: str | None
    body: str | None
    answered: bool
    created_at: datetime


class InboundMessagePayload(BaseModel):
    from_address: EmailStr
    from_name: str | None = None
    subject: str | None = None
    body: str | None = None
    message_id: str | None = None
    source_reference: str | None = None


@router.get("/", response_model=list[MessageOut])
async def list_messages(
    db: AsyncSession = Depends(get_db),
    only_inbound: bool = True,
    only_unanswered: bool = False,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
):
    query = select(EmailLog).order_by(EmailLog.created_at.desc())
    if only_inbound:
        query = query.where(EmailLog.direction == EmailDirection.INBOUND)
    if only_unanswered:
        query = query.where(EmailLog.answered == False)  # noqa: E712
    query = query.offset(offset).limit(limit)
    logs = (await db.execute(query)).scalars().all()

    # Batch-load candidates
    ids = {log.candidate_id for log in logs if log.candidate_id}
    candidates: dict[int, Candidate] = {}
    if ids:
        rows = (
            await db.execute(select(Candidate).where(Candidate.id.in_(ids)))
        ).scalars().all()
        candidates = {c.id: c for c in rows}

    out: list[MessageOut] = []
    for log in logs:
        cand = candidates.get(log.candidate_id) if log.candidate_id else None
        photo_url = (
            f"/api/candidates/{cand.id}/photo" if cand and cand.photo_url else None
        )
        out.append(
            MessageOut(
                id=log.id,
                candidate_id=log.candidate_id,
                candidate_name=(cand.full_name if cand else None),
                candidate_photo_url=photo_url,
                direction=log.direction,
                kind=log.kind,
                from_address=log.from_address,
                to_address=log.to_address,
                subject=log.subject,
                body=log.body,
                answered=log.answered,
                created_at=log.created_at,
            )
        )
    return out


def _verify_webhook_secret(provided: str | None) -> None:
    """Constant-time check of the X-Webhook-Secret header.

    If ``INBOUND_WEBHOOK_SECRET`` is unset, the check is a no-op so the
    endpoint stays open in dev. If set, callers MUST present a matching
    secret or the request is rejected with 401.
    """
    expected = (get_settings().inbound_webhook_secret or "").strip()
    if not expected:
        return
    if not provided or not hmac.compare_digest(expected, provided.strip()):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/inbound", response_model=MessageOut, status_code=201)
async def inbound_webhook(
    payload: InboundMessagePayload,
    db: AsyncSession = Depends(get_db),
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
):
    """Ingest a message from the external REST API / webapp.

    Authentication: requires the ``X-Webhook-Secret`` header to match
    ``INBOUND_WEBHOOK_SECRET`` from configuration when that secret is set.

    Matches by email to an existing candidate. If none exists, a placeholder
    profile is created so the conversation can still be tracked — but it will
    be in ``info_requested`` state and require follow-up.
    """
    _verify_webhook_secret(x_webhook_secret)
    email = payload.from_address.lower()
    candidate = (
        await db.execute(select(Candidate).where(Candidate.email.ilike(email)))
    ).scalar_one_or_none()

    if not candidate:
        result = await crm.upsert_from_inbound(
            db,
            parsed={},
            cv_text=None,
            cv_filename=None,
            cv_bytes=None,
            source=CandidateSource.EXTERNAL_API,
            source_reference=payload.source_reference or payload.message_id,
            fallback_email=email,
            fallback_name=payload.from_name,
        )
        candidate = result.candidate

    log = await crm.append_message(
        db,
        candidate=candidate,
        direction=EmailDirection.INBOUND,
        kind=EmailKind.REPLY,
        from_address=email,
        to_address=None,
        subject=payload.subject,
        body=payload.body,
        message_id=payload.message_id,
    )
    await db.commit()
    photo_url = (
        f"/api/candidates/{candidate.id}/photo" if candidate.photo_url else None
    )
    return MessageOut(
        id=log.id,
        candidate_id=candidate.id,
        candidate_name=candidate.full_name,
        candidate_photo_url=photo_url,
        direction=log.direction,
        kind=log.kind,
        from_address=log.from_address,
        to_address=log.to_address,
        subject=log.subject,
        body=log.body,
        answered=log.answered,
        created_at=log.created_at,
    )


@router.post("/{message_id}/read")
async def mark_read(
    message_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
):
    log = (
        await db.execute(select(EmailLog).where(EmailLog.id == message_id))
    ).scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Message not found")
    log.answered = bool(payload.get("answered", True))
    await db.commit()
    return {"id": log.id, "answered": log.answered}
