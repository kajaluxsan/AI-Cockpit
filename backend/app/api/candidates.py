"""Candidate (CRM profile) API."""

from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call_log import CallLog
from app.models.candidate import Candidate, CandidateSource, CandidateStatus
from app.models.chat_message import ChatMessage
from app.models.email_log import EmailDirection, EmailKind, EmailLog
from app.models.email_template import EmailTemplate
from app.models.job import Job, JobStatus
from app.schemas.candidate import (
    CandidateCreate,
    CandidateOut,
    CandidateUpdate,
    ProtocolEntry,
)
from app.services import crm, cv_parser, gdpr
from app.services.email_service import send_email
from app.services.email_templates import render_for_candidate
from app.services.linkedin_proxycurl import (
    ProxycurlError,
    ProxycurlNotConfigured,
    fetch_profile as fetch_linkedin_profile,
    merge_profile_into_candidate,
)
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


# ---------------------------------------------------------------------------
# Bulk actions — declared BEFORE ``/{candidate_id}`` so the "bulk" segment
# doesn't get parsed as a candidate id and rejected with 422. FastAPI
# matches routes in registration order.
# ---------------------------------------------------------------------------
class BulkIdsRequest(BaseModel):
    candidate_ids: list[int] = Field(default_factory=list)


class BulkEmailRequest(BaseModel):
    candidate_ids: list[int] = Field(min_length=1)
    template_id: int | None = None
    # Ad-hoc subject/body for the case where the recruiter wants to send
    # something one-off without first saving it as a template. One of
    # (template_id) or (subject + body) is required.
    subject: str | None = None
    body: str | None = None


class BulkEmailError(BaseModel):
    candidate_id: int
    reason: str


class BulkEmailResult(BaseModel):
    sent: int
    failed: int
    errors: list[BulkEmailError]


_CSV_COLUMNS: list[tuple[str, str]] = [
    ("id", "ID"),
    ("full_name", "Name"),
    ("email", "E-Mail"),
    ("phone", "Telefon"),
    ("location", "Ort"),
    ("headline", "Headline"),
    ("status", "Status"),
    ("source", "Quelle"),
    ("linkedin_url", "LinkedIn"),
    ("created_at", "Angelegt"),
    ("updated_at", "Aktualisiert"),
]


def _candidate_csv_row(c: Candidate) -> list[str]:
    def _s(val: Any) -> str:
        if val is None:
            return ""
        if hasattr(val, "value"):
            return str(val.value)
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val)

    return [
        _s(c.id),
        _s(c.full_name or f"{c.first_name or ''} {c.last_name or ''}".strip()),
        _s(c.email),
        _s(c.phone),
        _s(c.location),
        _s(c.headline),
        _s(c.status),
        _s(c.source),
        _s(c.linkedin_url),
        _s(c.created_at),
        _s(c.updated_at),
    ]


async def _load_candidates_for_bulk(
    db: AsyncSession, ids: list[int] | None
) -> list[Candidate]:
    """Load non-anonymised candidates for a bulk op.

    Passing ``None`` means "everything" (CSV export-all). Anonymised
    rows are always excluded — exporting or mailing a tombstoned record
    would defeat the point of the GDPR flow.
    """
    query = select(Candidate).where(Candidate.anonymised.is_(False))
    if ids is not None:
        if not ids:
            return []
        query = query.where(Candidate.id.in_(ids))
    query = query.order_by(Candidate.id.asc())
    return list((await db.execute(query)).scalars().all())


def _stream_csv(rows: list[Candidate], *, filename: str) -> StreamingResponse:
    """Shared CSV writer used by both export endpoints.

    Writes into an in-memory ``StringIO`` (the dataset is small enough
    that this is fine) and hands it back as a ``StreamingResponse`` with
    a ``Content-Disposition`` so browsers prompt a download.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([label for _, label in _CSV_COLUMNS])
    for row in rows:
        writer.writerow(_candidate_csv_row(row))
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/bulk/export")
async def bulk_export_all(db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Export every non-anonymised candidate as CSV (for People "export all")."""
    rows = await _load_candidates_for_bulk(db, None)
    logger.info(f"Bulk export: dumping {len(rows)} candidates (export-all)")
    return _stream_csv(rows, filename="candidates.csv")


@router.post("/bulk/export")
async def bulk_export_selected(
    payload: BulkIdsRequest, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Export the candidates whose ids appear in ``candidate_ids``."""
    rows = await _load_candidates_for_bulk(db, payload.candidate_ids)
    logger.info(f"Bulk export: dumping {len(rows)} selected candidates")
    return _stream_csv(rows, filename="candidates-selected.csv")


@router.post("/bulk/email", response_model=BulkEmailResult)
async def bulk_email(
    payload: BulkEmailRequest, db: AsyncSession = Depends(get_db)
) -> BulkEmailResult:
    """Send a templated email to every candidate in the selection.

    Behaviour:
      - If ``template_id`` is set, the template is rendered per-candidate
        (so {{first_name}} etc. are personalised) and used as-is.
      - Otherwise ``subject`` + ``body`` are required and sent verbatim
        (no placeholder expansion) — the recruiter typed them by hand in
        the bulk dialog.
      - Candidates without an email address, or who have been anonymised,
        are counted as failures with a clear reason.
      - Every successful send creates an ``EmailLog`` row so the protocol
        tab of each candidate shows the outbound message.
    """
    if payload.template_id is None and not (payload.subject and payload.body):
        raise HTTPException(
            status_code=400,
            detail="Either template_id or subject+body must be provided.",
        )

    template: EmailTemplate | None = None
    if payload.template_id is not None:
        template = await db.get(EmailTemplate, payload.template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")

    candidates = await _load_candidates_for_bulk(db, payload.candidate_ids)
    by_id = {c.id: c for c in candidates}

    sent = 0
    errors: list[BulkEmailError] = []

    for cid in payload.candidate_ids:
        c = by_id.get(cid)
        if c is None:
            errors.append(
                BulkEmailError(candidate_id=cid, reason="Not found or anonymised")
            )
            continue
        if not c.email:
            errors.append(
                BulkEmailError(candidate_id=cid, reason="No email address on record")
            )
            continue

        if template is not None:
            rendered = await render_for_candidate(db, template, c)
            subject, body = rendered.subject, rendered.body
        else:
            subject = payload.subject or ""
            body = payload.body or ""

        try:
            ok = await send_email(
                to_address=c.email, subject=subject, body=body
            )
        except Exception as exc:  # defensive — send_email already catches
            logger.exception(f"Bulk email: unexpected failure for candidate={cid}")
            ok = False
            errors.append(BulkEmailError(candidate_id=cid, reason=str(exc)[:200]))
            continue

        if not ok:
            errors.append(
                BulkEmailError(candidate_id=cid, reason="SMTP send failed")
            )
            continue

        db.add(
            EmailLog(
                candidate_id=c.id,
                direction=EmailDirection.OUTBOUND,
                kind=EmailKind.NOTIFICATION,
                from_address=None,
                to_address=c.email,
                subject=subject,
                body=body,
                answered=False,
            )
        )
        sent += 1

    await db.commit()
    logger.info(
        f"Bulk email: attempted={len(payload.candidate_ids)} sent={sent} failed={len(errors)}"
    )
    return BulkEmailResult(sent=sent, failed=len(errors), errors=errors)


@router.get("/stats/recent")
async def recent_stats_top(db: AsyncSession = Depends(get_db)):
    """Small tiles for the dashboard widget — count by status.

    Declared up here alongside the bulk routes so it also sits above
    ``/{candidate_id}`` and can't be shadowed by it.
    """
    rows = (
        await db.execute(
            select(Candidate.status, func.count(Candidate.id)).group_by(Candidate.status)
        )
    ).all()
    return {row[0].value: row[1] for row in rows}


# ---------------------------------------------------------------------------
# Per-candidate endpoints — all below this line match ``/{candidate_id}/*``
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# GDPR / Swiss FADP endpoints
# ---------------------------------------------------------------------------
@router.post("/{candidate_id}/anonymise", response_model=CandidateOut)
async def anonymise_candidate_endpoint(
    candidate_id: int, db: AsyncSession = Depends(get_db)
):
    """Right to be forgotten: blanks every PII field on the candidate and
    every related row (emails, chat, CV file on disk), keeping the id so
    historical counts and foreign keys stay intact. This action is
    irreversible — there is no undo."""
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.anonymised:
        # Idempotent — calling it twice is not an error
        return _serialize(candidate)
    await gdpr.anonymise_candidate(db, candidate)
    await db.commit()
    await db.refresh(candidate)
    return _serialize(candidate)


@router.post("/{candidate_id}/consent", response_model=CandidateOut)
async def record_consent_endpoint(
    candidate_id: int,
    source: str = Query(..., min_length=1, max_length=120),
    db: AsyncSession = Depends(get_db),
):
    """Record that the candidate has given consent for data processing.
    ``source`` is a short label identifying where the consent came from
    (e.g. ``webform``, ``email_reply``, ``manual``, ``phone``)."""
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    gdpr.record_consent(candidate, source=source)
    await db.commit()
    await db.refresh(candidate)
    return _serialize(candidate)


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
                recording_url=c.recording_url,
                duration_seconds=c.duration_seconds,
                call_sid=c.twilio_call_sid,
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


# ---------------------------------------------------------------------------
# LinkedIn (Proxycurl) import
# ---------------------------------------------------------------------------


class LinkedInImportRequest(BaseModel):
    """Request body for the Proxycurl importer.

    ``linkedin_url`` overrides whatever is stored on the candidate — useful
    when the recruiter pastes a freshly-found profile URL. If omitted, we
    fall back to ``candidate.linkedin_url``.
    """

    linkedin_url: str | None = None


class LinkedInImportResult(BaseModel):
    candidate: CandidateOut
    updated_fields: list[str]


@router.post(
    "/{candidate_id}/import-linkedin", response_model=LinkedInImportResult
)
async def import_linkedin_profile(
    candidate_id: int,
    payload: LinkedInImportRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> LinkedInImportResult:
    """Fetch a LinkedIn profile via Proxycurl and merge it into the candidate.

    Returns the updated candidate plus the list of fields that were actually
    touched, so the frontend can show a clear "3 Felder aktualisiert" toast
    instead of a vague success message.

    Refuses to run against anonymised candidates (GDPR right to be
    forgotten — we must never re-hydrate PII once deleted).
    """
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.anonymised:
        raise HTTPException(
            status_code=409,
            detail="Candidate is anonymised (GDPR) and cannot be re-imported",
        )

    linkedin_url = (
        (payload.linkedin_url.strip() if payload and payload.linkedin_url else None)
        or candidate.linkedin_url
    )
    if not linkedin_url:
        raise HTTPException(
            status_code=400,
            detail="No LinkedIn URL provided or stored on candidate",
        )

    try:
        profile = await fetch_linkedin_profile(linkedin_url)
    except ProxycurlNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProxycurlError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    updated = merge_profile_into_candidate(candidate, profile)
    # Persist the LinkedIn URL itself so subsequent imports don't need the
    # recruiter to re-enter it.
    if candidate.linkedin_url != linkedin_url:
        candidate.linkedin_url = linkedin_url
        if "linkedin_url" not in updated:
            updated.append("linkedin_url")

    await db.commit()
    await db.refresh(candidate)
    logger.info(
        f"LinkedIn import: candidate={candidate_id} updated={updated}"
    )
    return LinkedInImportResult(
        candidate=_serialize(candidate), updated_fields=updated
    )


