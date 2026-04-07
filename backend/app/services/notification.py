"""Recruiter notification service."""

from __future__ import annotations

from loguru import logger

from app.config import get_settings
from app.models.candidate import Candidate
from app.models.job import Job
from app.services.email_service import send_email


async def notify_recruiter_match(
    candidate: Candidate, job: Job, score: float, rationale: str
) -> None:
    settings = get_settings()
    recipient = settings.email_from_address
    if not recipient:
        logger.info("No recruiter notification address configured")
        return
    subject = f"[RecruiterAI] Neuer Match {score:.0f}%: {candidate.full_name} ↔ {job.title}"
    body = (
        f"Neuer Kandidaten-Match gefunden:\n\n"
        f"Kandidat: {candidate.full_name} ({candidate.email})\n"
        f"Stelle:   {job.title} @ {job.company or '-'}\n"
        f"Score:    {score:.0f}%\n\n"
        f"Begründung:\n{rationale}\n\n"
        f"Dashboard: {settings.vite_api_url}\n"
    )
    await send_email(to_address=recipient, subject=subject, body=body)


async def notify_recruiter_call_complete(
    candidate: Candidate, summary: str, interest: str | None
) -> None:
    settings = get_settings()
    recipient = settings.email_from_address
    if not recipient:
        return
    subject = (
        f"[RecruiterAI] Anruf beendet: {candidate.full_name} (Interesse: {interest or '-'})"
    )
    body = (
        f"Telefonat mit {candidate.full_name} wurde abgeschlossen.\n\n"
        f"Interesse: {interest or 'unbekannt'}\n\n"
        f"Zusammenfassung:\n{summary}\n"
    )
    await send_email(to_address=recipient, subject=subject, body=body)
