"""Dashboard / aggregated stats API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call_log import CallLog, CallStatus
from app.models.candidate import Candidate, CandidateStatus
from app.models.email_log import EmailLog
from app.models.job import Job, JobStatus
from app.models.match import Match

router = APIRouter()


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=7)

    new_today = (
        await db.execute(
            select(func.count(Candidate.id)).where(Candidate.created_at >= today)
        )
    ).scalar_one()

    open_jobs = (
        await db.execute(
            select(func.count(Job.id)).where(Job.status == JobStatus.OPEN)
        )
    ).scalar_one()

    matches_this_week = (
        await db.execute(
            select(func.count(Match.id)).where(Match.created_at >= week_start)
        )
    ).scalar_one()

    calls_today = (
        await db.execute(
            select(func.count(CallLog.id)).where(CallLog.created_at >= today)
        )
    ).scalar_one()

    completed_calls = (
        await db.execute(
            select(func.count(CallLog.id)).where(CallLog.status == CallStatus.COMPLETED)
        )
    ).scalar_one()

    placed_candidates = (
        await db.execute(
            select(func.count(Candidate.id)).where(
                Candidate.status == CandidateStatus.PLACED
            )
        )
    ).scalar_one()

    return {
        "new_candidates_today": new_today,
        "open_jobs": open_jobs,
        "matches_this_week": matches_this_week,
        "calls_today": calls_today,
        "completed_calls": completed_calls,
        "placed_candidates": placed_candidates,
    }


@router.get("/activity")
async def recent_activity(db: AsyncSession = Depends(get_db), limit: int = 25):
    """Combined recent activity feed across emails, calls, matches, candidates."""
    activity: list[dict[str, Any]] = []

    cands = (
        await db.execute(
            select(Candidate).order_by(Candidate.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    for c in cands:
        activity.append(
            {
                "type": "candidate_created",
                "timestamp": c.created_at,
                "title": f"Neuer Kandidat: {c.full_name or c.email or 'Unbekannt'}",
                "candidate_id": c.id,
                "source": c.source.value if c.source else None,
            }
        )

    matches = (
        await db.execute(select(Match).order_by(Match.created_at.desc()).limit(limit))
    ).scalars().all()
    for m in matches:
        activity.append(
            {
                "type": "match_created",
                "timestamp": m.created_at,
                "title": f"Match erstellt (Score {m.score:.0f}%)",
                "candidate_id": m.candidate_id,
                "job_id": m.job_id,
            }
        )

    calls = (
        await db.execute(select(CallLog).order_by(CallLog.created_at.desc()).limit(limit))
    ).scalars().all()
    for call in calls:
        activity.append(
            {
                "type": "call",
                "timestamp": call.created_at,
                "title": f"Anruf {call.status.value}",
                "candidate_id": call.candidate_id,
                "call_id": call.id,
            }
        )

    emails = (
        await db.execute(select(EmailLog).order_by(EmailLog.created_at.desc()).limit(limit))
    ).scalars().all()
    for em in emails:
        activity.append(
            {
                "type": f"email_{em.direction.value}",
                "timestamp": em.created_at,
                "title": em.subject or "(kein Betreff)",
                "candidate_id": em.candidate_id,
            }
        )

    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    return activity[:limit]
