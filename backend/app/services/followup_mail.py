"""Generate and send follow-up emails for missing candidate info."""

from __future__ import annotations

from loguru import logger

from app.config import get_settings
from app.models.candidate import Candidate
from app.services.claude_client import get_claude_client
from app.services.email_service import send_email
from app.utils.prompts import FOLLOWUP_EMAIL_PROMPT


async def generate_followup_email(
    candidate: Candidate, missing_fields: list[str]
) -> dict[str, str]:
    settings = get_settings()
    claude = get_claude_client()

    language = (candidate.language or "de").lower()
    language_label = "Deutsch" if language == "de" else "English"

    prompt = FOLLOWUP_EMAIL_PROMPT.format(
        agent_name=settings.agent_name,
        company_name=settings.company_name,
        missing_fields=", ".join(missing_fields),
        candidate_name=candidate.full_name or ("Bewerber" if language == "de" else "Applicant"),
        language=language,
        language_label=language_label,
    )

    try:
        result = await claude.complete_json(prompt)
    except Exception as exc:
        logger.exception(f"Failed to generate follow-up mail: {exc}")
        # Fallback so the user still gets a sensible mail
        result = {
            "subject": (
                "Vielen Dank für Ihre Bewerbung – kurze Rückfrage"
                if language == "de"
                else "Thanks for your application – a quick question"
            ),
            "body": (
                "Guten Tag,\n\nvielen Dank für Ihre Bewerbung. Um Sie optimal "
                "vermitteln zu können, fehlen uns noch ein paar Angaben: "
                f"{', '.join(missing_fields)}.\n\nKönnten Sie uns diese kurz zukommen "
                f"lassen?\n\nBeste Grüsse\n{settings.agent_name}\n{settings.company_name}"
                if language == "de"
                else "Hi,\n\nThanks for your application. To best place you we still "
                f"need a few details: {', '.join(missing_fields)}.\n\nCould you share "
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
