"""CRM layer: upsert candidates from CV / message intake, required-field gating.

The CRM contract is:

1. Every inbound CV or message is funnelled through :func:`upsert_from_inbound`.
2. The function looks up an existing candidate by email (case-insensitive). If
   one exists, the profile is updated in place — the existing protocol
   (email / call / chat history) stays attached to that single CRM record.
3. If no candidate exists, a new profile is inserted **only** if all CRM
   required fields (configured via ``CRM_REQUIRED_FIELDS``) are present.
   Otherwise the candidate is stored in the PARSED-pending state and a
   follow-up mail is sent asking for the missing info.
4. Any inbound message (email, external webhook) is always appended to the
   protocol via :func:`append_message`.

This module is intentionally free of FastAPI imports so it can be reused by
background workers, webhooks and the sync REST endpoints.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.candidate import Candidate, CandidateSource, CandidateStatus
from app.models.email_log import EmailDirection, EmailKind, EmailLog

CV_STORAGE_DIR = Path(os.getenv("CV_STORAGE_DIR", "/data/cv"))


@dataclass
class UpsertResult:
    candidate: Candidate
    created: bool
    missing_required: list[str]


def _required_missing(data: dict[str, Any]) -> list[str]:
    """Return the list of CRM required fields that are missing from ``data``."""
    settings = get_settings()
    missing: list[str] = []
    for field in settings.crm_required_field_list:
        value = data.get(field)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field)
    return missing


def _merge(existing: Candidate, data: dict[str, Any]) -> None:
    """Update ``existing`` candidate from parsed ``data`` — only fills empty
    slots, never overwrites human-edited values."""
    mapping = {
        "first_name": data.get("first_name"),
        "last_name": data.get("last_name"),
        "full_name": data.get("full_name"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "address": data.get("address"),
        "location": data.get("location"),
        "language": data.get("language"),
        "headline": data.get("headline"),
        "summary": data.get("summary"),
        "skills": data.get("skills"),
        "experience_years": data.get("experience_years"),
        "education": data.get("education"),
        "work_history": data.get("work_history"),
        "salary_expectation": data.get("salary_expectation"),
        "salary_currency": data.get("salary_currency"),
        "availability": data.get("availability"),
        "languages_spoken": data.get("languages_spoken"),
    }
    for key, value in mapping.items():
        if value in (None, [], ""):
            continue
        current = getattr(existing, key, None)
        if current in (None, [], ""):
            setattr(existing, key, value)
    existing.updated_at = datetime.now(timezone.utc)


async def _find_by_email(db: AsyncSession, email: str | None) -> Candidate | None:
    if not email:
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    q = select(Candidate).where(Candidate.email.ilike(normalized))
    return (await db.execute(q)).scalar_one_or_none()


async def upsert_from_inbound(
    db: AsyncSession,
    *,
    parsed: dict[str, Any],
    cv_text: str | None,
    cv_filename: str | None,
    cv_bytes: bytes | None,
    source: CandidateSource,
    source_reference: str | None,
    fallback_email: str | None = None,
    fallback_name: str | None = None,
) -> UpsertResult:
    """Upsert a candidate based on parsed CV / message data.

    Returns the resulting Candidate, whether it was freshly created, and the
    list of required fields that are still missing (empty list if complete).
    """
    email = parsed.get("email") or fallback_email

    # Merge fallback name into parsed data if missing
    if not parsed.get("full_name") and fallback_name:
        parsed["full_name"] = fallback_name
    missing = _required_missing(
        {
            "first_name": parsed.get("first_name"),
            "last_name": parsed.get("last_name"),
            "email": email,
            "phone": parsed.get("phone"),
        }
    )

    existing = await _find_by_email(db, email)
    if existing:
        _merge(existing, parsed)
        if cv_text and not existing.cv_text:
            existing.cv_text = cv_text[:200000]
        cv_path = _store_cv(cv_filename, cv_bytes)
        if cv_path and not existing.cv_attachment_path:
            existing.cv_attachment_path = cv_path
            existing.cv_filename = cv_filename
        if not missing and existing.status == CandidateStatus.INFO_REQUESTED:
            existing.status = CandidateStatus.PARSED
            existing.missing_fields = None
        await db.flush()
        return UpsertResult(candidate=existing, created=False, missing_required=missing)

    # New candidate
    cv_path = _store_cv(cv_filename, cv_bytes)
    candidate = Candidate(
        first_name=parsed.get("first_name"),
        last_name=parsed.get("last_name"),
        full_name=parsed.get("full_name"),
        email=email,
        phone=parsed.get("phone"),
        address=parsed.get("address"),
        location=parsed.get("location"),
        language=parsed.get("language"),
        headline=parsed.get("headline"),
        summary=parsed.get("summary"),
        skills=parsed.get("skills"),
        experience_years=parsed.get("experience_years"),
        education=parsed.get("education"),
        work_history=parsed.get("work_history"),
        salary_expectation=parsed.get("salary_expectation"),
        salary_currency=parsed.get("salary_currency"),
        availability=parsed.get("availability"),
        languages_spoken=parsed.get("languages_spoken"),
        source=source,
        source_reference=source_reference,
        cv_text=cv_text[:200000] if cv_text else None,
        cv_attachment_path=cv_path,
        cv_filename=cv_filename,
        status=(
            CandidateStatus.INFO_REQUESTED if missing else CandidateStatus.PARSED
        ),
        missing_fields=missing or None,
    )
    db.add(candidate)
    await db.flush()
    return UpsertResult(candidate=candidate, created=True, missing_required=missing)


def _store_cv(filename: str | None, data: bytes | None) -> str | None:
    """Persist the CV file to disk and return the stored path."""
    if not data or not filename:
        return None
    try:
        CV_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning(f"Cannot create CV storage dir: {exc}")
        return None
    ext = Path(filename).suffix or ".bin"
    slug = f"{uuid.uuid4().hex}{ext}"
    path = CV_STORAGE_DIR / slug
    try:
        path.write_bytes(data)
    except Exception as exc:
        logger.exception(f"Failed to store CV file: {exc}")
        return None
    return str(path)


async def append_message(
    db: AsyncSession,
    *,
    candidate: Candidate | None,
    direction: EmailDirection,
    kind: EmailKind,
    from_address: str | None,
    to_address: str | None,
    subject: str | None,
    body: str | None,
    message_id: str | None = None,
    attachments_count: int = 0,
) -> EmailLog:
    """Append a message entry to the candidate protocol."""
    log = EmailLog(
        candidate_id=candidate.id if candidate else None,
        direction=direction,
        kind=kind,
        message_id=message_id,
        from_address=from_address,
        to_address=to_address,
        subject=(subject or "")[:500] or None,
        body=(body or "")[:50000] or None,
        attachments_count=attachments_count,
    )
    db.add(log)
    await db.flush()
    return log
