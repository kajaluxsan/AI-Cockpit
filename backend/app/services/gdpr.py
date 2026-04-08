"""GDPR / Swiss FADP compliance helpers.

The Swiss Federal Act on Data Protection (FADP, revised 2023) and the EU
GDPR both require a recruiter to be able to:

1. **Erase** personal data on request ("right to be forgotten").
2. **Limit retention** — personal data must not be kept longer than is
   necessary for the declared purpose. For a recruiter cockpit, the
   pragmatic interpretation is: once a candidate is rejected, the record
   has a finite life measured in months, not years.
3. **Prove consent** was given for data processing, at least with an
   audit trail of when and via which channel.

This module does not try to be a full compliance framework. It gives the
application three primitives:

- :func:`anonymise_candidate` — blanks every PII field on a single
  ``Candidate`` record in place. Id is preserved so foreign keys in
  ``call_logs`` / ``email_logs`` / ``chat_messages`` keep pointing to
  something, which matters for audit trails.
- :func:`purge_expired_candidates` — scans ``candidates`` for rows that
  have been in status=REJECTED long enough (see ``GDPR_RETENTION_DAYS``)
  and runs :func:`anonymise_candidate` on each.
- :func:`record_consent` — timestamps the candidate's consent and stores
  a short ``source`` label (e.g. "webform", "email_reply", "manual").

The purge worker in ``app/workers/gdpr_purge.py`` calls
:func:`purge_expired_candidates` on a timer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.candidate import Candidate, CandidateStatus


# Placeholder value used for every anonymised text field. We want it
# loud and unmistakable so a recruiter looking at an anonymised record
# immediately understands they cannot contact the person anymore.
_TOMBSTONE = "[anonymised]"


async def anonymise_candidate(db: AsyncSession, candidate: Candidate) -> None:
    """Blank every PII field on the given candidate in place.

    The id, created_at and status are preserved so downstream rows (email
    logs, call logs, matches) keep a valid foreign key and reporting
    queries don't silently drop historical counts.

    The CV file on disk is also removed if it exists — that's where the
    richest PII lives and it's the most obvious thing a data subject
    would ask us to delete.
    """
    logger.info(
        f"Anonymising candidate id={candidate.id} "
        f"(was status={candidate.status.value if candidate.status else 'null'})"
    )

    # Wipe the CV file on disk, if any. Do this first so a crash in the
    # middle leaves the DB record still flagged as pending.
    if candidate.cv_attachment_path:
        try:
            path = Path(candidate.cv_attachment_path)
            if path.exists():
                path.unlink()
                logger.debug(f"Deleted CV file at {path}")
        except Exception as exc:
            logger.warning(
                f"Failed to delete CV file for candidate {candidate.id}: {exc}"
            )

    # Same for the extracted profile photo.
    if candidate.photo_url:
        try:
            path = Path(candidate.photo_url)
            if path.exists():
                path.unlink()
                logger.debug(f"Deleted photo file at {path}")
        except Exception as exc:
            logger.warning(
                f"Failed to delete photo file for candidate {candidate.id}: {exc}"
            )

    candidate.first_name = _TOMBSTONE
    candidate.last_name = _TOMBSTONE
    candidate.full_name = _TOMBSTONE
    candidate.email = None  # email is unique-ish; keep it null, not placeholder
    candidate.phone = None
    candidate.address = None
    candidate.location = None
    candidate.headline = None
    candidate.summary = None
    candidate.skills = None
    candidate.education = None
    candidate.work_history = None
    candidate.salary_expectation = None
    candidate.salary_currency = None
    candidate.availability = None
    candidate.languages_spoken = None
    candidate.cv_text = None
    candidate.cv_attachment_path = None
    candidate.cv_filename = None
    candidate.photo_url = None
    candidate.notes = None
    candidate.linkedin_url = None
    candidate.source_reference = None

    candidate.anonymised = True
    candidate.deletion_requested_at = candidate.deletion_requested_at or datetime.now(
        timezone.utc
    )

    # Blank the chat + email history bodies too — we keep the rows so
    # counts are preserved, but the free-text fields are where PII hides.
    from app.models.chat_message import ChatMessage
    from app.models.email_log import EmailLog

    await db.execute(
        ChatMessage.__table__.update()
        .where(ChatMessage.candidate_id == candidate.id)
        .values(content=_TOMBSTONE, tool_payload=None)
    )
    await db.execute(
        EmailLog.__table__.update()
        .where(EmailLog.candidate_id == candidate.id)
        .values(
            subject=_TOMBSTONE,
            body=_TOMBSTONE,
            from_address=None,
            to_address=None,
        )
    )


async def purge_expired_candidates(db: AsyncSession) -> int:
    """Anonymise every candidate whose retention window has expired.

    Returns the number of records that were anonymised in this run.
    """
    settings = get_settings()
    days = settings.gdpr_retention_days
    if days <= 0:
        logger.debug("GDPR_RETENTION_DAYS=0 — automatic purge disabled")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Eligible: rejected longer than ``days`` and not already anonymised.
    # ``updated_at`` is the pragmatic clock — it's bumped whenever the
    # recruiter changes the status. It drifts if the record is touched
    # for unrelated reasons, but in practice that's rare and the error is
    # always on the side of "retain slightly longer", which is safer.
    query = (
        select(Candidate)
        .where(Candidate.anonymised.is_(False))
        .where(
            or_(
                Candidate.retain_until.isnot(None)
                & (Candidate.retain_until < datetime.now(timezone.utc)),
                (Candidate.status == CandidateStatus.REJECTED)
                & (Candidate.updated_at < cutoff),
            )
        )
    )
    rows = (await db.execute(query)).scalars().all()
    if not rows:
        return 0

    logger.info(
        f"GDPR purge: found {len(rows)} candidate(s) past retention window "
        f"(retention={days} days)"
    )
    for cand in rows:
        await anonymise_candidate(db, cand)
    await db.commit()
    return len(rows)


def record_consent(candidate: Candidate, source: str) -> None:
    """Timestamp the candidate's consent. Idempotent — the first recorded
    consent wins, subsequent calls are a no-op."""
    if candidate.consent_given_at is not None:
        return
    candidate.consent_given_at = datetime.now(timezone.utc)
    candidate.consent_source = source[:120]
    logger.info(
        f"Consent recorded for candidate id={candidate.id} via source={source}"
    )
