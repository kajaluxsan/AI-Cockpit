"""Twilio webhook endpoints (voice TwiML, status callback, media stream)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, get_db
from app.models.call_log import CallLog, CallStatus
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.match import Match
from app.services import voice_agent

router = APIRouter()


@router.post("/twilio/voice", response_class=Response)
async def twilio_voice_webhook(
    candidate_id: int = Query(...),
    match_id: int | None = Query(default=None),
    objective: str | None = Query(default=None),
):
    """Twilio hits this when the call connects. We return TwiML that opens
    a bidirectional Media Stream back to our WebSocket handler.

    ``objective`` is forwarded from ``initiate_call`` (e.g. a reason from the
    per-candidate AI chat like "Frag nach Gehalt und Verfügbarkeit"). It is
    piped into the voice conversation system prompt so the voice agent
    pursues that specific goal during the call.
    """
    twiml = voice_agent.generate_voice_twiml(
        candidate_id=candidate_id, match_id=match_id, objective=objective
    )
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status")
async def twilio_status_webhook(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    To: str | None = Form(default=None),
    From: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"Twilio status callback: {CallSid} -> {CallStatus}")
    result = await db.execute(select(CallLog).where(CallLog.twilio_call_sid == CallSid))
    call = result.scalar_one_or_none()
    if not call:
        return {"ok": True, "found": False}
    try:
        call.status = _map_twilio_status(CallStatus)
    except Exception:
        pass
    if CallStatus == "completed" and not call.ended_at:
        call.ended_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.websocket("/twilio/stream")
async def twilio_media_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("Twilio media stream connected")

    async def get_session_for_candidate(
        candidate_id: int,
        match_id: int | None,
        objective: str | None = None,
    ):
        async with SessionLocal() as db:
            cand_q = select(Candidate).where(Candidate.id == candidate_id)
            cand = (await db.execute(cand_q)).scalar_one_or_none()
            job: Job | None = None
            if match_id:
                m = (
                    await db.execute(select(Match).where(Match.id == match_id))
                ).scalar_one_or_none()
                if m:
                    job = (
                        await db.execute(select(Job).where(Job.id == m.job_id))
                    ).scalar_one_or_none()
            return voice_agent.CallSession(
                candidate=cand,
                job=job,
                language=(cand.language if cand and cand.language else "de"),
                objective=objective,
            )

    try:
        await voice_agent.handle_media_stream(
            websocket, get_session_for_candidate=get_session_for_candidate
        )
    except WebSocketDisconnect:
        logger.info("Twilio media stream disconnected")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _map_twilio_status(status: str) -> CallStatus:
    mapping = {
        "queued": CallStatus.INITIATED,
        "initiated": CallStatus.INITIATED,
        "ringing": CallStatus.RINGING,
        "in-progress": CallStatus.IN_PROGRESS,
        "completed": CallStatus.COMPLETED,
        "busy": CallStatus.BUSY,
        "no-answer": CallStatus.NO_ANSWER,
        "failed": CallStatus.FAILED,
        "canceled": CallStatus.CANCELED,
    }
    return mapping.get(status.lower(), CallStatus.INITIATED)
