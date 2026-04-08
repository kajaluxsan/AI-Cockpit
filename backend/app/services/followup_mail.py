"""Generate and send follow-up emails for missing candidate info."""

from __future__ import annotations

from loguru import logger

from app.config import get_settings
from app.models.candidate import Candidate
from app.services.claude_client import get_claude_client
from app.services.email_service import send_email
from app.utils.prompts import FOLLOWUP_EMAIL_PROMPT


def _humanize_field(name: str, language: str) -> str:
    """Map raw field names to a friendly label for the prompt."""
    de = {
        "first_name": "Vorname",
        "last_name": "Nachname",
        "email": "E-Mail",
        "phone": "Telefonnummer",
        "address": "Adresse",
        "skills": "Skills / Kenntnisse",
        "experience_years": "Berufserfahrung in Jahren",
        "salary_expectation": "Gehaltsvorstellung",
        "availability": "Verfügbarkeit / Eintrittsdatum",
        "location": "Wohnort",
    }
    en = {
        "first_name": "first name",
        "last_name": "last name",
        "email": "email address",
        "phone": "phone number",
        "address": "address",
        "skills": "skills",
        "experience_years": "years of experience",
        "salary_expectation": "salary expectation",
        "availability": "availability / start date",
        "location": "location",
    }
    table = de if language == "de" else en
    return table.get(name, name)


def _summarise_recent_jobs(candidate: Candidate, limit: int = 2) -> str:
    work = candidate.work_history or []
    if not work:
        return "—"
    parts: list[str] = []
    for entry in work[:limit]:
        if not isinstance(entry, dict):
            continue
        title = (entry.get("title") or "").strip()
        company = (entry.get("company") or "").strip()
        if title and company:
            parts.append(f"{title} @ {company}")
        elif title:
            parts.append(title)
        elif company:
            parts.append(company)
    return ", ".join(parts) if parts else "—"


async def generate_followup_email(
    candidate: Candidate, missing_fields: list[str]
) -> dict[str, str]:
    settings = get_settings()
    claude = get_claude_client()

    language = (candidate.language or "de").lower()
    language_label = "Deutsch" if language == "de" else "English"

    pretty_missing = ", ".join(_humanize_field(f, language) for f in missing_fields)
    skills = candidate.skills or []
    skills_preview = ", ".join(skills[:6]) if skills else "—"
    name_for_greeting = (
        candidate.first_name
        or candidate.full_name
        or ("Bewerber" if language == "de" else "Applicant")
    )

    prompt = FOLLOWUP_EMAIL_PROMPT.format(
        agent_name=settings.agent_name,
        company_name=settings.company_name,
        missing_fields=pretty_missing,
        candidate_name=name_for_greeting,
        language=language,
        language_label=language_label,
        headline=candidate.headline or "—",
        skills=skills_preview,
        recent_jobs=_summarise_recent_jobs(candidate),
    )

    try:
        result = await claude.complete_json(prompt)
    except Exception as exc:
        logger.exception(f"Failed to generate follow-up mail: {exc}")
        # Fallback so the user still gets a sensible mail
        greeting = (
            f"Guten Tag {candidate.first_name}" if candidate.first_name and language == "de"
            else f"Hi {candidate.first_name}" if candidate.first_name
            else "Guten Tag" if language == "de"
            else "Hi"
        )
        result = {
            "subject": (
                "Vielen Dank für Ihre Bewerbung – kurze Rückfrage"
                if language == "de"
                else "Thanks for your application – a quick question"
            ),
            "body": (
                f"{greeting},\n\nvielen Dank für Ihre Bewerbung. Um Sie optimal "
                "vermitteln zu können, fehlen uns noch ein paar Angaben: "
                f"{pretty_missing}.\n\nKönnten Sie uns diese kurz zukommen "
                f"lassen?\n\nBeste Grüsse\n{settings.agent_name}\n{settings.company_name}"
                if language == "de"
                else f"{greeting},\n\nThanks for your application. To best place you we still "
                f"need a few details: {pretty_missing}.\n\nCould you share "
                f"those with us briefly?\n\nBest regards\n{settings.agent_name}\n"
                f"{settings.company_name}"
            ),
        }

    return {"subject": result.get("subject", ""), "body": result.get("body", "")}


async def send_followup_email(
    candidate: Candidate, missing_fields: list[str]
) -> dict[str, str] | None:
    if not candidate.email:
        logger.info(f"No email for candidate {candidate.id}, skipping follow-up")
        return None
    mail = await generate_followup_email(candidate, missing_fields)
    sent = await send_email(
        to_address=candidate.email,
        subject=mail["subject"],
        body=mail["body"],
    )
    return mail if sent else None
