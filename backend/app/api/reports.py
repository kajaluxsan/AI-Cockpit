"""Reporting / pipeline metrics API.

Feeds the Reports dashboard in the frontend. Everything here is derived
at query-time from the ORM tables — no materialised views or caching.
At the scale this app runs (a single-digit number of recruiters, tens of
thousands of candidates) every metric here is a millisecond COUNT query,
so freshness trumps optimisation.

Metrics exposed:

- ``GET /pipeline``   — candidates grouped by status (funnel chart)
- ``GET /sources``    — candidates grouped by ``source`` (pie chart)
- ``GET /calls``      — call outcomes and conversion over N days
- ``GET /emails``     — inbound/outbound email volume over N days
- ``GET /timeseries`` — daily new-candidate counts over N days

All time-based endpoints take an optional ``days`` parameter (default 30,
max 365) so the UI can re-query when the recruiter changes the range.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call_log import CallDirection, CallLog, CallStatus
from app.models.candidate import Candidate, CandidateSource, CandidateStatus
from app.models.email_log import EmailDirection, EmailLog
from app.models.job import Job, JobStatus
from app.models.match import Match, MatchStatus

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _window_start(days: int) -> datetime:
    """Start of the reporting window. Bounded 1..365 for sanity."""
    days = max(1, min(days, 365))
    return datetime.now(timezone.utc) - timedelta(days=days)


# ---------------------------------------------------------------------------
# Pipeline funnel
# ---------------------------------------------------------------------------
@router.get("/pipeline")
async def pipeline(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Count candidates at each pipeline stage.

    Returns a mapping + a total so the UI can render a funnel without
    re-summing on the client. Stages that currently have zero candidates
    are still returned (as 0) so the chart doesn't jitter as stages pop
    in and out.
    """
    rows = (
        await db.execute(
            select(Candidate.status, func.count(Candidate.id)).group_by(Candidate.status)
        )
    ).all()
    counts: dict[str, int] = {s.value: 0 for s in CandidateStatus}
    for status_value, count in rows:
        key = status_value.value if hasattr(status_value, "value") else str(status_value)
        counts[key] = int(count)

    return {
        "stages": counts,
        "total": sum(counts.values()),
    }


# ---------------------------------------------------------------------------
# Source distribution
# ---------------------------------------------------------------------------
@router.get("/sources")
async def sources(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Count candidates per source (email / linkedin / external_api / manual)."""
    rows = (
        await db.execute(
            select(Candidate.source, func.count(Candidate.id)).group_by(Candidate.source)
        )
    ).all()
    counts: dict[str, int] = {s.value: 0 for s in CandidateSource}
    for source_value, count in rows:
        key = source_value.value if hasattr(source_value, "value") else str(source_value)
        counts[key] = int(count)
    return {"sources": counts, "total": sum(counts.values())}


# ---------------------------------------------------------------------------
# Call outcomes
# ---------------------------------------------------------------------------
@router.get("/calls")
async def calls(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Call volume + outcome breakdown over the last ``days`` days.

    ``answered_rate`` is derived as completed / (completed + no_answer +
    busy + failed). Rows outside those statuses (initiated, ringing) are
    excluded from the denominator because they're still in flight.
    """
    since = _window_start(days)
    rows = (
        await db.execute(
            select(CallLog.status, func.count(CallLog.id))
            .where(CallLog.created_at >= since)
            .group_by(CallLog.status)
        )
    ).all()
    by_status: dict[str, int] = {s.value: 0 for s in CallStatus}
    for status_value, count in rows:
        key = status_value.value if hasattr(status_value, "value") else str(status_value)
        by_status[key] = int(count)

    total = sum(by_status.values())
    finalised = (
        by_status.get(CallStatus.COMPLETED.value, 0)
        + by_status.get(CallStatus.NO_ANSWER.value, 0)
        + by_status.get(CallStatus.BUSY.value, 0)
        + by_status.get(CallStatus.FAILED.value, 0)
    )
    answered = by_status.get(CallStatus.COMPLETED.value, 0)
    answered_rate = (answered / finalised) if finalised else 0.0

    # Inbound vs outbound split
    dir_rows = (
        await db.execute(
            select(CallLog.direction, func.count(CallLog.id))
            .where(CallLog.created_at >= since)
            .group_by(CallLog.direction)
        )
    ).all()
    by_direction: dict[str, int] = {d.value: 0 for d in CallDirection}
    for dir_value, count in dir_rows:
        key = dir_value.value if hasattr(dir_value, "value") else str(dir_value)
        by_direction[key] = int(count)

    return {
        "days": days,
        "total": total,
        "by_status": by_status,
        "by_direction": by_direction,
        "answered_rate": round(answered_rate, 3),
    }


# ---------------------------------------------------------------------------
# Email volume
# ---------------------------------------------------------------------------
@router.get("/emails")
async def emails(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Inbound vs outbound email volume over the last ``days`` days."""
    since = _window_start(days)
    rows = (
        await db.execute(
            select(EmailLog.direction, func.count(EmailLog.id))
            .where(EmailLog.created_at >= since)
            .group_by(EmailLog.direction)
        )
    ).all()
    by_direction: dict[str, int] = {d.value: 0 for d in EmailDirection}
    for dir_value, count in rows:
        key = dir_value.value if hasattr(dir_value, "value") else str(dir_value)
        by_direction[key] = int(count)
    return {
        "days": days,
        "by_direction": by_direction,
        "total": sum(by_direction.values()),
    }


# ---------------------------------------------------------------------------
# Daily time-series — new candidates per day
# ---------------------------------------------------------------------------
@router.get("/timeseries")
async def timeseries(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Number of candidates created per day over the window.

    We group in Python rather than in SQL so the query is portable across
    backends (SQLite in dev, PostgreSQL in prod) without having to juggle
    ``date_trunc`` vs ``strftime``. N is bounded to 365 above so the
    in-process loop can't blow up.
    """
    since = _window_start(days)
    rows = (
        await db.execute(
            select(Candidate.created_at).where(Candidate.created_at >= since)
        )
    ).all()

    # Pre-seed every day in the window with 0 so the chart has a flat
    # baseline instead of missing days.
    buckets: dict[str, int] = {}
    day = since.replace(hour=0, minute=0, second=0, microsecond=0)
    end = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    while day <= end:
        buckets[day.date().isoformat()] = 0
        day += timedelta(days=1)

    for (created_at,) in rows:
        key = created_at.date().isoformat()
        if key in buckets:
            buckets[key] += 1

    series = [{"date": k, "count": v} for k, v in sorted(buckets.items())]
    return {"days": days, "series": series, "total": sum(buckets.values())}


# ---------------------------------------------------------------------------
# Top-level summary (used by the reports landing tiles)
# ---------------------------------------------------------------------------
@router.get("/summary")
async def summary(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """A small bag of KPIs for the reports page header tiles."""
    since = _window_start(days)

    new_candidates = (
        await db.execute(
            select(func.count(Candidate.id)).where(Candidate.created_at >= since)
        )
    ).scalar_one()
    new_matches = (
        await db.execute(
            select(func.count(Match.id)).where(Match.created_at >= since)
        )
    ).scalar_one()
    placements = (
        await db.execute(
            select(func.count(Match.id)).where(
                Match.status == MatchStatus.PLACED, Match.updated_at >= since
            )
        )
    ).scalar_one()
    open_jobs = (
        await db.execute(
            select(func.count(Job.id)).where(Job.status == JobStatus.OPEN)
        )
    ).scalar_one()

    # Conversion: matches that ended in PLACED out of all matches created
    # in the window. Only meaningful for longer windows — short ranges
    # (say 7d) will almost always be zero because the placement happens
    # weeks after the initial match.
    conversion = (placements / new_matches) if new_matches else 0.0

    return {
        "days": days,
        "new_candidates": int(new_candidates),
        "new_matches": int(new_matches),
        "placements": int(placements),
        "open_jobs": int(open_jobs),
        "placement_rate": round(conversion, 3),
    }
