"""Generate and send follow-up emails for missing candidate info."""

from __future__ import annotations

from loguru import logger

from app.config import get_settings
from app.models.candidate import Candidate
from app.services.claude_client import get_claude_client
from app.services.email_service import send_email
from app.utils.prompts import FOLLOWUP_EMAIL_PROMPT


_FIELD_LABELS: dict[str, dict[str, str]] = {
    "de": {
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
    },
    "en": {
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
    },
    "fr": {
        "first_name": "prénom",
        "last_name": "nom de famille",
        "email": "adresse e-mail",
        "phone": "numéro de téléphone",
        "address": "adresse",
        "skills": "compétences",
        "experience_years": "années d'expérience",
        "salary_expectation": "prétention salariale",
        "availability": "disponibilité / date d'entrée",
        "location": "lieu de résidence",
    },
    "it": {
        "first_name": "nome",
        "last_name": "cognome",
        "email": "indirizzo e-mail",
        "phone": "numero di telefono",
        "address": "indirizzo",
        "skills": "competenze",
        "experience_years": "anni di esperienza",
        "salary_expectation": "aspettativa salariale",
        "availability": "disponibilità / data di inizio",
        "location": "luogo di residenza",
    },
}

_LANGUAGE_LABEL = {
    "de": "Deutsch",
    "en": "English",
    "fr": "Français",
    "it": "Italiano",
}


def _humanize_field(name: str, language: str) -> str:
    """Map raw field names to a friendly label for the prompt."""
    table = _FIELD_LABELS.get(language, _FIELD_LABELS["en"])
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
    if language not in _LANGUAGE_LABEL:
        language = "de"
    language_label = _LANGUAGE_LABEL[language]

    pretty_missing = ", ".join(_humanize_field(f, language) for f in missing_fields)
    skills = candidate.skills or []
    skills_preview = ", ".join(skills[:6]) if skills else "—"
    fallback_name = {
        "de": "Bewerber",
        "en": "Applicant",
        "fr": "Candidat",
        "it": "Candidato",
    }[language]
    name_for_greeting = (
        candidate.first_name or candidate.full_name or fallback_name
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
        result = _fallback_email(
            candidate, language, pretty_missing, settings.agent_name, settings.company_name
        )

    return {"subject": result.get("subject", ""), "body": result.get("body", "")}


def _fallback_email(
    candidate: Candidate,
    language: str,
    pretty_missing: str,
    agent_name: str,
    company_name: str,
) -> dict[str, str]:
    """Language-aware fallback when Claude is unavailable."""
    fn = candidate.first_name
    if language == "de":
        greeting = f"Guten Tag {fn}" if fn else "Guten Tag"
        return {
            "subject": "Vielen Dank für Ihre Bewerbung – kurze Rückfrage",
            "body": (
                f"{greeting},\n\nvielen Dank für Ihre Bewerbung. Um Sie "
                f"optimal vermitteln zu können, fehlen uns noch ein paar "
                f"Angaben: {pretty_missing}.\n\nKönnten Sie uns diese kurz "
                f"zukommen lassen?\n\nBeste Grüsse\n{agent_name}\n{company_name}"
            ),
        }
    if language == "fr":
        greeting = f"Bonjour {fn}" if fn else "Bonjour"
        return {
            "subject": "Merci pour votre candidature – une petite question",
            "body": (
                f"{greeting},\n\nmerci pour votre candidature. Afin de "
                f"pouvoir vous proposer la meilleure opportunité, il nous "
                f"manque encore quelques informations : {pretty_missing}.\n\n"
                f"Pourriez-vous nous les communiquer brièvement ?\n\n"
                f"Cordialement\n{agent_name}\n{company_name}"
            ),
        }
    if language == "it":
        greeting = f"Buongiorno {fn}" if fn else "Buongiorno"
        return {
            "subject": "Grazie per la sua candidatura – una breve domanda",
            "body": (
                f"{greeting},\n\ngrazie per la sua candidatura. Per poterle "
                f"proporre l'opportunità migliore ci mancano ancora alcune "
                f"informazioni: {pretty_missing}.\n\nPotrebbe inviarcele "
                f"brevemente?\n\nCordiali saluti\n{agent_name}\n{company_name}"
            ),
        }
    # Default English
    greeting = f"Hi {fn}" if fn else "Hi"
    return {
        "subject": "Thanks for your application – a quick question",
        "body": (
            f"{greeting},\n\nthanks for your application. To best place you "
            f"we still need a few details: {pretty_missing}.\n\nCould you "
            f"share those with us briefly?\n\nBest regards\n{agent_name}\n"
            f"{company_name}"
        ),
    }


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
