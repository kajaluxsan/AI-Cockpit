"""Call API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
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
