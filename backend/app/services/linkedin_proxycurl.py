"""Proxycurl LinkedIn profile importer.

Fetches a public LinkedIn profile via the Proxycurl Person Profile API and
normalises the response into our ``Candidate`` shape. The endpoint is
``GET https://nubela.co/proxycurl/api/v2/linkedin?url=<linkedin_profile_url>``
and returns a fairly rich JSON document we only partially consume.

Only fields that are currently empty on the candidate are filled in; the
recruiter's manual edits are never overwritten. Skills from Proxycurl are
merged (de-duplicated) with existing ones.

The service is a no-op when ``linkedin_scraper_api_key`` is unset — calling
code should treat that as a soft error (HTTP 503) so the UI can nudge the
admin to configure the integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from app.config import get_settings
from app.models.candidate import Candidate, CandidateSource


class ProxycurlError(RuntimeError):
    """Raised for any Proxycurl-side or network failure."""


class ProxycurlNotConfigured(ProxycurlError):
    """Raised when the Proxycurl API key is missing from settings."""


@dataclass
class ProxycurlProfile:
    """Subset of Proxycurl Person Profile fields we care about."""

    raw: dict[str, Any]
    full_name: str | None
    first_name: str | None
    last_name: str | None
    headline: str | None
    summary: str | None
    location: str | None
    country: str | None
    profile_pic_url: str | None
    skills: list[str]
    languages: list[str]
    work_history: list[dict[str, Any]]
    education: list[dict[str, Any]]
    experience_years: float | None


def _coerce_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return str(v)


def _years_between(
    start: dict[str, Any] | None, end: dict[str, Any] | None
) -> float:
    """Rough duration in years between two Proxycurl date dicts.

    Proxycurl dates look like ``{"day": 1, "month": 6, "year": 2019}``.
    ``end`` may be null (still working there), in which case we treat it as
    the start (0 years) — we can't extrapolate to "now" here because this
    module is supposed to be pure (no datetime side effects).
    """
    if not start or not end:
        return 0.0
    sy = start.get("year")
    sm = start.get("month") or 1
    ey = end.get("year")
    em = end.get("month") or 1
    if not sy or not ey:
        return 0.0
    return max(0.0, (ey - sy) + (em - sm) / 12.0)


def _parse_profile(data: dict[str, Any]) -> ProxycurlProfile:
    full_name = _coerce_str(data.get("full_name")) or " ".join(
        filter(None, [data.get("first_name"), data.get("last_name")])
    ).strip() or None

    # Work history → list of {title, company, start, end, location}
    experiences = data.get("experiences") or []
    work_history: list[dict[str, Any]] = []
    total_years = 0.0
    for exp in experiences:
        work_history.append(
            {
                "title": _coerce_str(exp.get("title")),
                "company": _coerce_str(exp.get("company")),
                "location": _coerce_str(exp.get("location")),
                "description": _coerce_str(exp.get("description")),
                "start": exp.get("starts_at"),
                "end": exp.get("ends_at"),
            }
        )
        total_years += _years_between(exp.get("starts_at"), exp.get("ends_at"))

    # Education
    edu_raw = data.get("education") or []
    education: list[dict[str, Any]] = []
    for e in edu_raw:
        education.append(
            {
                "school": _coerce_str(e.get("school")),
                "degree": _coerce_str(e.get("degree_name")),
                "field": _coerce_str(e.get("field_of_study")),
                "start": e.get("starts_at"),
                "end": e.get("ends_at"),
            }
        )

    # Skills — Proxycurl returns a list of strings under "skills".
    skills_raw = data.get("skills") or []
    skills: list[str] = [s for s in (_coerce_str(x) for x in skills_raw) if s]

    # Languages — list of dicts {name, proficiency} in "languages_and_proficiencies"
    langs_raw = (
        data.get("languages_and_proficiencies")
        or data.get("languages")
        or []
    )
    languages: list[str] = []
    for lang in langs_raw:
        if isinstance(lang, str):
            name = _coerce_str(lang)
        elif isinstance(lang, dict):
            name = _coerce_str(lang.get("name") or lang.get("language"))
        else:
            name = None
        if name:
            languages.append(name)

    location_bits = [
        _coerce_str(data.get("city")),
        _coerce_str(data.get("state")),
    ]
    location = ", ".join(b for b in location_bits if b) or None

    return ProxycurlProfile(
        raw=data,
        full_name=full_name,
        first_name=_coerce_str(data.get("first_name")),
        last_name=_coerce_str(data.get("last_name")),
        headline=_coerce_str(data.get("headline") or data.get("occupation")),
        summary=_coerce_str(data.get("summary")),
        location=location,
        country=_coerce_str(data.get("country_full_name") or data.get("country")),
        profile_pic_url=_coerce_str(data.get("profile_pic_url")),
        skills=skills,
        languages=languages,
        work_history=work_history,
        education=education,
        experience_years=round(total_years, 1) if total_years else None,
    )


async def fetch_profile(linkedin_url: str) -> ProxycurlProfile:
    """Fetch and parse a LinkedIn profile via Proxycurl.

    Raises ``ProxycurlNotConfigured`` when the API key is missing, or
    ``ProxycurlError`` for any HTTP / JSON failure.
    """
    settings = get_settings()
    api_key = settings.linkedin_scraper_api_key
    if not api_key:
        raise ProxycurlNotConfigured(
            "linkedin_scraper_api_key is not configured"
        )

    base = settings.linkedin_scraper_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"url": linkedin_url, "use_cache": "if-present"}

    logger.info(f"Proxycurl: fetching profile {linkedin_url}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(base, headers=headers, params=params)
    except httpx.HTTPError as exc:
        raise ProxycurlError(f"Network error contacting Proxycurl: {exc}") from exc

    if resp.status_code == 401:
        raise ProxycurlError("Proxycurl rejected the API key (401)")
    if resp.status_code == 404:
        raise ProxycurlError("LinkedIn profile not found (404)")
    if resp.status_code >= 400:
        raise ProxycurlError(
            f"Proxycurl returned HTTP {resp.status_code}: {resp.text[:200]}"
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise ProxycurlError("Proxycurl returned non-JSON body") from exc

    return _parse_profile(data)


def merge_profile_into_candidate(
    candidate: Candidate, profile: ProxycurlProfile
) -> list[str]:
    """Fill empty fields on ``candidate`` from the parsed Proxycurl profile.

    Returns the list of field names that were actually updated, so the
    caller can report them back to the UI / log line.

    Non-empty candidate fields are left untouched (recruiter edits win).
    Skills are merged (union, case-insensitive de-dup).
    """
    updated: list[str] = []

    def _set(attr: str, value: Any) -> None:
        current = getattr(candidate, attr, None)
        if value and not current:
            setattr(candidate, attr, value)
            updated.append(attr)

    _set("first_name", profile.first_name)
    _set("last_name", profile.last_name)
    _set("full_name", profile.full_name)
    _set("headline", profile.headline)
    _set("summary", profile.summary)
    _set("location", profile.location)

    # Only overwrite work/education when currently empty — we don't want
    # to clobber structured data that may already have been extracted
    # from a CV.
    if profile.work_history and not candidate.work_history:
        candidate.work_history = profile.work_history
        updated.append("work_history")
    if profile.education and not candidate.education:
        candidate.education = profile.education
        updated.append("education")
    if profile.experience_years and not candidate.experience_years:
        candidate.experience_years = profile.experience_years
        updated.append("experience_years")

    # Merge skills (union, case-insensitive).
    if profile.skills:
        existing = candidate.skills or []
        seen = {str(s).strip().lower() for s in existing if s}
        merged = list(existing)
        added = 0
        for s in profile.skills:
            key = s.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(s)
                added += 1
        if added:
            candidate.skills = merged
            updated.append("skills")

    # Merge languages_spoken similarly.
    if profile.languages:
        existing_l = candidate.languages_spoken or []
        seen_l = {str(s).strip().lower() for s in existing_l if s}
        merged_l = list(existing_l)
        added_l = 0
        for s in profile.languages:
            key = s.strip().lower()
            if key and key not in seen_l:
                seen_l.add(key)
                merged_l.append(s)
                added_l += 1
        if added_l:
            candidate.languages_spoken = merged_l
            updated.append("languages_spoken")

    # Tag the source so the UI can show "imported from LinkedIn" even
    # when the candidate originally came from an email.
    if candidate.source == CandidateSource.MANUAL and updated:
        candidate.source = CandidateSource.LINKEDIN
        updated.append("source")

    return updated
