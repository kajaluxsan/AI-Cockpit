"""Match API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.match import Match, MatchStatus
from app.schemas.match import MatchCreate, MatchOut, MatchUpdate
from app.services import matching_engine

router = APIRouter()


@router.get("/", response_model=list[MatchOut])
async def list_matches(
    db: AsyncSession = Depends(get_db),
    status: MatchStatus | None = None,
    candidate_id: int | None = None,
    job_id: int | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
):
    query = select(Match).order_by(Match.created_at.desc())
    if status:
        query = query.where(Match.status == status)
    if candidate_id:
        query = query.where(Match.candidate_id == candidate_id)
    if job_id:
        query = query.where(Match.job_id == job_id)
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=MatchOut, status_code=201)
async def create_match(payload: MatchCreate, db: AsyncSession = Depends(get_db)):
    match = Match(**payload.model_dump())
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match


@router.patch("/{match_id}", response_model=MatchOut)
async def update_match(
    match_id: int, payload: MatchUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Match).where(Match.id == match_id))
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(match, k, v)
    await db.commit()
    await db.refresh(match)
    return match


@router.post("/score/{candidate_id}/{job_id}", response_model=MatchOut)
async def score_and_create(
    candidate_id: int, job_id: int, db: AsyncSession = Depends(get_db)
):
    cand = (await db.execute(select(Candidate).where(Candidate.id == candidate_id))).scalar_one_or_none()
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if not cand or not job:
        raise HTTPException(status_code=404, detail="Candidate or Job not found")
    result = await matching_engine.score_match(cand, job)
    match = Match(
        candidate_id=candidate_id,
        job_id=job_id,
        score=result.score,
        score_breakdown=matching_engine.to_dict(result),
        rationale=result.rationale,
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match
