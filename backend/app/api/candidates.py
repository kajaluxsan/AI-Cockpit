"""Candidate (CRM profile) API."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call_log import CallLog
from app.models.candidate import Candidate, CandidateSource, CandidateStatus
from app.models.chat_message import ChatMessage
from app.models.email_log import EmailDirection, EmailLog
from app.models.job import Job, JobStatus
from app.schemas.candidate import (
    CandidateCreate,
    CandidateOut,
    CandidateUpdate,
    ProtocolEntry,
)
from app.services import crm, cv_parser
from app.services.matching_engine import find_matches_for_candidate, to_dict
from app.services.photo_extractor import PHOTO_STORAGE_DIR, extract_photo

router = APIRouter()


def _serialize(c: Candidate) -> CandidateOut:
    return CandidateOut.from_orm_candidate(c)


@router.get("/", response_model=list[CandidateOut])
async def list_candidates(
    db: AsyncSession = Depends(get_db),
    status: CandidateStatus | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    sort: str = Query(default="recent", pattern="^(recent|name)$"),
):
    """List candidates with free-text search.

    The query (``q``) matches on first/last/full name, email, phone and
    address — this is what powers the top-bar search in the frontend.
    """
    query = select(Candidate)
    if status:
        query = query.where(Candidate.status == status)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Candidate.full_name.ilike(like),
                Candidate.first_name.ilike(like),
                Candidate.last_name.ilike(like),
                Candidate.email.ilike(like),
                Candidate.phone.ilike(like),
                Candidate.address.ilike(like),
                Candidate.location.ilike(like),
            )
        )
    if sort == "name":
        query = query.order_by(Candidate.last_name.asc().nullslast(), Candidate.first_name.asc())
    else:
        query = query.order_by(Candidate.updated_at.desc())
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return [_serialize(c) for c in result.scalars().all()]


@router.post("/", response_model=CandidateOut, status_code=201)
async def create_candidate(
    payload: CandidateCreate, db: AsyncSession = Depends(get_db)
):
    candidate = Candidate(**payload.model_dump())
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return _serialize(candidate)


@router.post("/upload-cv", response_model=CandidateOut, status_code=201)
async def upload_cv(
    file: UploadFile = File(...),
    email: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Manual CV upload — runs the CV through Claude, then goes through the
    CRM upsert path so the dedupe-by-email logic applies."""
    data = await file.read()
    text = cv_parser.extract_text_from_attachment(file.filename or "cv.pdf", data)
    parsed = await cv_parser.parse_cv_text(text) if text.strip() else {}

    result = await crm.upsert_from_inbound(
        db,
        parsed=parsed or {},
        cv_text=text,
        cv_filename=file.filename,
        cv_bytes=data,
        source=CandidateSource.MANUAL,
        source_reference=None,
        fallback_email=email,
    )
    await db.commit()
    await db.refresh(result.candidate)
    return _serialize(result.candidate)


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _serialize(candidate)


@router.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(candidate, k, v)
    await db.commit()
    await db.refresh(candidate)
    return _serialize(candidate)


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    await db.delete(candidate)
    await db.commit()


@router.get("/{candidate_id}/photo")
async def get_photo(candidate_id: int, db: AsyncSession = Depends(get_db)):
    """Stream the candidate profile photo from local storage."""
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate or not candidate.photo_url:
        raise HTTPException(status_code=404, detail="No photo for this candidate")
    path = Path(candidate.photo_url)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Photo file missing on disk")
    suffix = path.suffix.lower().lstrip(".")
    media = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media)


@router.post("/{candidate_id}/photo", response_model=CandidateOut)
async def upload_photo(
    candidate_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Manually upload a profile photo for a candidate.

    Used by recruiters when CV photo extraction missed or there is no CV
    attached. Replaces any existing photo.
    """
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image upload")

    try:
        PHOTO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage unavailable: {exc}")
    ext = Path(file.filename or "").suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    target = PHOTO_STORAGE_DIR / f"{uuid.uuid4().hex}{ext}"
    target.write_bytes(data)

    # Best-effort cleanup of the previous photo
    if candidate.photo_url:
        try:
            old = Path(candidate.photo_url)
            if old.exists() and old.is_relative_to(PHOTO_STORAGE_DIR):
                old.unlink()
        except Exception:
            pass

    candidate.photo_url = str(target)
    await db.commit()
    await db.refresh(candidate)
    return _serialize(candidate)


@router.post("/{candidate_id}/extract-photo", response_model=CandidateOut)
async def reextract_photo(
    candidate_id: int, db: AsyncSession = Depends(get_db)
):
    """Re-run photo extraction on the stored CV. Useful after the heuristic
    has been tuned, or if the original ingest missed the photo."""
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.cv_attachment_path:
        raise HTTPException(status_code=400, detail="No CV stored for candidate")
    path = Path(candidate.cv_attachment_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="CV file missing on disk")
    photo_path = extract_photo(candidate.cv_filename or path.name, path.read_bytes())
    if not photo_path:
        raise HTTPException(status_code=404, detail="No photo found in CV")
    candidate.photo_url = photo_path
    await db.commit()
    await db.refresh(candidate)
    return _serialize(candidate)


@router.get("/{candidate_id}/cv")
async def download_cv(candidate_id: int, db: AsyncSession = Depends(get_db)):
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.cv_attachment_path:
        raise HTTPException(status_code=404, detail="No CV stored for this candidate")
    path = Path(candidate.cv_attachment_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="CV file missing on disk")
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(
        path,
        media_type=media,
        filename=candidate.cv_filename or path.name,
    )


@router.get("/{candidate_id}/protocol", response_model=list[ProtocolEntry])
async def protocol(candidate_id: int, db: AsyncSession = Depends(get_db)):
    """Return a unified timeline for the candidate (emails, calls, chat)."""
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    entries: list[ProtocolEntry] = []

    emails = (
        await db.execute(
            select(EmailLog)
            .where(EmailLog.candidate_id == candidate_id)
            .order_by(EmailLog.created_at.desc())
        )
    ).scalars().all()
    for em in emails:
        kind = "email_inbound" if em.direction == EmailDirection.INBOUND else "email_outbound"
        entries.append(
            ProtocolEntry(
                kind=kind,
                title=em.subject or f"{em.kind.value}",
                body=em.body,
                direction=em.direction.value,
                status=em.kind.value,
                created_at=em.created_at,
                reference_id=em.id,
            )
        )

    calls = (
        await db.execute(
            select(CallLog)
            .where(CallLog.candidate_id == candidate_id)
            .order_by(CallLog.created_at.desc())
        )
    ).scalars().all()
    for c in calls:
        entries.append(
            ProtocolEntry(
                kind="call",
                title=f"Call → {c.to_number or '—'}",
                body=c.summary or c.transcript,
                status=c.status.value,
                direction=c.direction.value,
                created_at=c.created_at,
                reference_id=c.id,
            )
        )

    chats = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.candidate_id == candidate_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    for m in chats:
        if m.role.value == "system":
            continue
        entries.append(
            ProtocolEntry(
                kind="chat",
                title=f"AI-Chat · {m.role.value}",
                body=m.content,
                status=m.tool_name,
                created_at=m.created_at,
                reference_id=m.id,
            )
        )

    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries


@router.get("/{candidate_id}/matching-jobs", response_model=list[dict[str, Any]])
async def matching_jobs(
    candidate_id: int,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return open jobs ranked by fit for this candidate."""
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    jobs = (
        await db.execute(
            select(Job).where(Job.status == JobStatus.OPEN).limit(limit * 2)
        )
    ).scalars().all()
    ranked = await find_matches_for_candidate(candidate, list(jobs))
    return [
        {
            "job": {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
            },
            "match": to_dict(result),
        }
        for job, result in ranked[:limit]
    ]


@router.post("/{candidate_id}/notes", response_model=CandidateOut)
async def update_notes(
    candidate_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate.notes = payload.get("notes")
    await db.commit()
    await db.refresh(candidate)
    return _serialize(candidate)


@router.get("/stats/recent")
async def recent_stats(db: AsyncSession = Depends(get_db)):
    """Small tiles for the dashboard widget — count by status."""
    rows = (
        await db.execute(
            select(Candidate.status, func.count(Candidate.id)).group_by(Candidate.status)
        )
    ).all()
    return {row[0].value: row[1] for row in rows}
