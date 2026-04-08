"""Job API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.candidate import Candidate
from app.models.job import Job, JobStatus
from app.schemas.candidate import CandidateOut
from app.schemas.job import JobCreate, JobOut, JobUpdate
from app.services.matching_engine import find_matches_for_job, to_dict

router = APIRouter()


@router.get("/", response_model=list[JobOut])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    status: JobStatus | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    query = select(Job).order_by(Job.created_at.desc())
    if status:
        query = query.where(Job.status == status)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Job.title.ilike(like),
                Job.company.ilike(like),
                Job.location.ilike(like),
                Job.description.ilike(like),
            )
        )
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=JobOut, status_code=201)
async def create_job(payload: JobCreate, db: AsyncSession = Depends(get_db)):
    job = Job(**payload.model_dump())
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}", response_model=JobOut)
async def update_job(
    job_id: int, payload: JobUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(job, k, v)
    await db.commit()
    await db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.delete(job)
    await db.commit()


@router.get("/{job_id}/candidates", response_model=list[dict[str, Any]])
async def matching_candidates(
    job_id: int,
    limit: int = Query(default=25, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return candidates ranked by fit for this job."""
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    pool = (
        await db.execute(select(Candidate).limit(limit * 4))
    ).scalars().all()
    ranked = await find_matches_for_job(job, list(pool))
    return [
        {
            "candidate": CandidateOut.from_orm_candidate(cand).model_dump(mode="json"),
            "match": to_dict(result),
        }
        for cand, result in ranked[:limit]
    ]
