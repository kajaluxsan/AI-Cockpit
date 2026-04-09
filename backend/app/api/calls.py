"""Call API."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call_log import CallLog, CallStatus
from app.models.candidate import Candidate
from app.schemas.call import CallLogOut, InitiateCallRequest
from app.services import voice_agent

router = APIRouter()


@router.get("/", response_model=list[CallLogOut])
async def list_calls(
    db: AsyncSession = Depends(get_db),
    candidate_id: int | None = None,
    status: CallStatus | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    query = select(CallLog).order_by(CallLog.created_at.desc())
    if candidate_id:
        query = query.where(CallLog.candidate_id == candidate_id)
    if status:
        query = query.where(CallLog.status == status)
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{call_id}", response_model=CallLogOut)
async def get_call(call_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallLog).where(CallLog.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@router.post("/initiate", response_model=CallLogOut, status_code=201)
async def initiate(payload: InitiateCallRequest, db: AsyncSession = Depends(get_db)):
    cand = (
        await db.execute(select(Candidate).where(Candidate.id == payload.candidate_id))
    ).scalar_one_or_none()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    to_number = payload.to_number or cand.phone
    if not to_number:
        raise HTTPException(status_code=400, detail="No phone number for candidate")

    try:
        twilio_info = voice_agent.initiate_call(
            to_number=to_number,
            candidate_id=cand.id,
            match_id=payload.match_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Twilio error: {exc}") from exc

    log = CallLog(
        candidate_id=cand.id,
        match_id=payload.match_id,
        twilio_call_sid=twilio_info["sid"],
        from_number=twilio_info["from"],
        to_number=twilio_info["to"],
        status=CallStatus.INITIATED,
        detected_language=payload.language,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.post("/{call_id}/hangup", response_model=CallLogOut)
async def hangup_call_endpoint(
    call_id: int, db: AsyncSession = Depends(get_db)
) -> CallLog:
    """End a live call by hitting Twilio's ``calls.update(status=completed)``.

    Used by the "Take over" / "End call" button in the UI so a recruiter
    can abort the AI conversation mid-flight. The Twilio status-callback
    webhook will still fire with ``completed`` afterwards, so we only do
    the minimum local bookkeeping here (mark ``ended_at``) to avoid
    racing with the callback.
    """
    row = (
        await db.execute(select(CallLog).where(CallLog.id == call_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if not row.twilio_call_sid:
        raise HTTPException(
            status_code=400, detail="Call has no Twilio SID to terminate"
        )
    # Terminal state already? Nothing to do — return the row as-is so
    # the UI doesn't show a misleading error after double-clicks.
    if row.status in (
        CallStatus.COMPLETED,
        CallStatus.CANCELED,
        CallStatus.FAILED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
    ):
        logger.info(
            f"Hangup: call id={row.id} already in terminal state {row.status.value}"
        )
        return row

    try:
        voice_agent.hangup_call(row.twilio_call_sid)
    except Exception as exc:
        logger.exception(f"Hangup: Twilio update failed for call={row.id}")
        raise HTTPException(status_code=502, detail=f"Twilio error: {exc}") from exc

    # Optimistic local update; the Twilio status callback will
    # overwrite with the authoritative terminal status shortly.
    row.status = CallStatus.CANCELED
    if not row.ended_at:
        row.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    logger.info(f"Hangup: call id={row.id} sid={row.twilio_call_sid} ended by user")
    return row
