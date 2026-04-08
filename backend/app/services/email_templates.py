"""Email template rendering.

Templates are plain text with ``{{placeholder}}`` markers. We intentionally
do NOT use Jinja2 or any other templating engine:

- The placeholders are a closed, well-known set (see docstring of
  :class:`app.models.email_template.EmailTemplate`).
- Using a real engine would open a sandbox-escape surface for anyone who
  can edit templates in the UI. Even a safe sandbox is a liability we
  don't need.
- Simple ``str.replace`` is easy to audit: there is no code path that
  evaluates user-controlled strings as logic.

The rendering function returns the fully expanded subject + body, with
``{{signature}}`` automatically resolved against the language-matching
signature template (the one with ``is_signature=True``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.candidate import Candidate
from app.models.email_template import EmailTemplate


@dataclass
class RenderedEmail:
    subject: str
    body: str


# Placeholder pattern: matches ``{{name}}`` with optional inner whitespace.
# We anchor on double-braces to avoid accidentally matching JSON snippets
# or CSS the recruiter might paste in.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.IGNORECASE)


def _candidate_placeholders(candidate: Candidate) -> dict[str, str]:
    """Derive the placeholder -> value dict from a candidate record."""
    settings = get_settings()
    # Some candidates only have a parsed full_name; split it for the
    # first/last slots instead of leaving them empty.
    first = candidate.first_name or ""
    last = candidate.last_name or ""
    full = candidate.full_name or f"{first} {last}".strip()
    if not first and full:
        parts = full.split(None, 1)
        first = parts[0]
        if len(parts) == 2 and not last:
            last = parts[1]

    # ``skills`` is stored as a JSON list in the DB. Join for display.
    skills_list = candidate.skills or []
    if isinstance(skills_list, str):
        skills = skills_list
    else:
        skills = ", ".join(str(s) for s in skills_list)

    # ``work_history`` is a JSON list of dicts (title + company + years).
    # Build a short plain-text listing for the template slot.
    wh = candidate.work_history or []
    if isinstance(wh, list):
        rows: list[str] = []
        for entry in wh[:3]:
            if isinstance(entry, dict):
                title = entry.get("title") or entry.get("position") or ""
                company = entry.get("company") or entry.get("employer") or ""
                rows.append(f"{title} @ {company}".strip(" @"))
        recent_jobs = "; ".join(r for r in rows if r)
    else:
        recent_jobs = ""

    return {
        "first_name": first,
        "last_name": last,
        "full_name": full or first or last or "",
        "headline": candidate.headline or "",
        "skills": skills,
        "recent_jobs": recent_jobs,
        "agent_name": settings.agent_name,
        "company_name": settings.company_name,
    }


def _substitute(text: str, values: dict[str, str]) -> str:
    """Replace every ``{{name}}`` in ``text`` with ``values[name]``.

    Unknown placeholders are left in place so the recruiter notices in
    the preview and can fix the template instead of silently sending a
    half-empty email. This is intentional — we prefer "{{foo}}" in the
    preview over a polished email that mysteriously omits a field.
    """

    def repl(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        return values.get(name, match.group(0))

    return _PLACEHOLDER_RE.sub(repl, text)


async def _load_signature(db: AsyncSession, language: str) -> str:
    """Return the plain-text signature block for a given language.

    If several signatures exist for the same language (shouldn't, but
    we don't enforce it in the schema), pick the most recently updated
    one so "latest edit wins". Empty string if nothing is defined.
    """
    row = (
        await db.execute(
            select(EmailTemplate)
            .where(EmailTemplate.is_signature.is_(True))
            .where(EmailTemplate.language == language)
            .order_by(EmailTemplate.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row.body if row else ""


async def render_for_candidate(
    db: AsyncSession,
    template: EmailTemplate,
    candidate: Candidate,
    extra: dict[str, str] | None = None,
) -> RenderedEmail:
    """Render ``template`` against ``candidate``.

    The ``extra`` dict lets callers inject ad-hoc placeholders (e.g. a
    job title when sending from a match screen) without having to
    piggyback onto the candidate model.
    """
    values = _candidate_placeholders(candidate)
    if extra:
        values.update(extra)

    # Expand {{signature}} first so nested placeholders inside the
    # signature itself (e.g. {{agent_name}}) get substituted too.
    signature = await _load_signature(db, template.language)
    values["signature"] = _substitute(signature, values)

    subject = _substitute(template.subject, values)
    body = _substitute(template.body, values)
    return RenderedEmail(subject=subject, body=body)


async def render_preview(
    db: AsyncSession,
    template: EmailTemplate,
    sample_values: dict[str, str] | None = None,
) -> RenderedEmail:
    """Render a template with placeholder sample data for the UI preview."""
    settings = get_settings()
    defaults = {
        "first_name": "Anna",
        "last_name": "Beispiel",
        "full_name": "Anna Beispiel",
        "headline": "Senior Fullstack Developer",
        "skills": "Python, TypeScript, AWS",
        "recent_jobs": "Senior Dev @ BeispielAG (2022-2025)",
        "agent_name": settings.agent_name,
        "company_name": settings.company_name,
    }
    if sample_values:
        defaults.update(sample_values)

    signature = await _load_signature(db, template.language)
    defaults["signature"] = _substitute(signature, defaults)

    return RenderedEmail(
        subject=_substitute(template.subject, defaults),
        body=_substitute(template.body, defaults),
    )
