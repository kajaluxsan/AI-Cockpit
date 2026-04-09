"""Candidate <-> Job matching engine.

Combines deterministic scoring with semantic Claude analysis for the best of
both worlds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.config import get_settings
from app.models.candidate import Candidate
from app.models.job import Job
from app.services import vector_index
from app.services.claude_client import get_claude_client
from app.utils.prompts import MATCH_ANALYSIS_PROMPT


@dataclass
class MatchResult:
    score: float
    breakdown: dict[str, float]
    rationale: str
    matched_skills: list[str]
    missing_skills: list[str]


WEIGHTS = {
    "skills_match": 0.40,
    "experience_match": 0.20,
    "location_match": 0.15,
    "salary_match": 0.15,
    "availability_match": 0.10,
}


def _heuristic_skill_overlap(
    candidate_skills: list[str], job_skills: list[str]
) -> tuple[float, list[str], list[str]]:
    if not job_skills:
        return 100.0, [], []
    cand_lower = {s.lower().strip() for s in (candidate_skills or [])}
    matched = []
    missing = []
    for skill in job_skills:
        s_low = skill.lower().strip()
        # consider partial substring matches as well
        if any(s_low in c or c in s_low for c in cand_lower):
            matched.append(skill)
        else:
            missing.append(skill)
    score = (len(matched) / len(job_skills)) * 100.0
    return score, matched, missing


def _experience_score(candidate_years: float | None, required: float | None) -> float:
    if not required:
        return 100.0
    if candidate_years is None:
        return 50.0
    if candidate_years >= required:
        return 100.0
    return max(0.0, (candidate_years / required) * 100.0)


def _location_score(candidate_loc: str | None, job_loc: str | None) -> float:
    if not job_loc:
        return 100.0
    if not candidate_loc:
        return 50.0
    if candidate_loc.lower().strip() == job_loc.lower().strip():
        return 100.0
    if any(part in job_loc.lower() for part in candidate_loc.lower().split()):
        return 75.0
    return 40.0


def _salary_score(candidate_expect: int | None, job_min: int | None, job_max: int | None) -> float:
    if not (job_min or job_max) or candidate_expect is None:
        return 100.0
    upper = job_max or job_min
    lower = job_min or job_max
    if upper is None:
        return 100.0
    if candidate_expect <= upper:
        return 100.0
    # gradient down
    diff_pct = (candidate_expect - upper) / max(upper, 1)
    return max(0.0, 100.0 - diff_pct * 200.0)


def _availability_score(availability: str | None) -> float:
    if not availability:
        return 60.0
    text = availability.lower()
    if any(w in text for w in ("sofort", "ab sofort", "asap", "immediately", "now")):
        return 100.0
    return 75.0


def heuristic_score(candidate: Candidate, job: Job) -> MatchResult:
    skill_score, matched, missing = _heuristic_skill_overlap(
        candidate.skills or [], job.required_skills or []
    )
    exp_score = _experience_score(candidate.experience_years, job.min_experience_years)
    loc_score = _location_score(candidate.location, job.location)
    sal_score = _salary_score(candidate.salary_expectation, job.salary_min, job.salary_max)
    avail_score = _availability_score(candidate.availability)

    breakdown = {
        "skills_match": skill_score,
        "experience_match": exp_score,
        "location_match": loc_score,
        "salary_match": sal_score,
        "availability_match": avail_score,
    }
    weighted = sum(breakdown[k] * WEIGHTS[k] for k in WEIGHTS)
    rationale = (
        f"Skills {skill_score:.0f}%, Erfahrung {exp_score:.0f}%, "
        f"Standort {loc_score:.0f}%, Gehalt {sal_score:.0f}%, "
        f"Verfügbarkeit {avail_score:.0f}%."
    )
    return MatchResult(
        score=round(weighted, 1),
        breakdown=breakdown,
        rationale=rationale,
        matched_skills=matched,
        missing_skills=missing,
    )


async def semantic_score(candidate: Candidate, job: Job) -> MatchResult | None:
    """Use Claude for semantic matching. Returns None on failure."""
    try:
        candidate_payload = {
            "name": candidate.full_name,
            "location": candidate.location,
            "skills": candidate.skills,
            "experience_years": candidate.experience_years,
            "salary_expectation": candidate.salary_expectation,
            "salary_currency": candidate.salary_currency,
            "availability": candidate.availability,
            "summary": candidate.summary,
        }
        job_payload = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description,
            "required_skills": job.required_skills,
            "nice_to_have_skills": job.nice_to_have_skills,
            "min_experience_years": job.min_experience_years,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
        }
        prompt = MATCH_ANALYSIS_PROMPT.format(
            candidate=json.dumps(candidate_payload, ensure_ascii=False, indent=2),
            job=json.dumps(job_payload, ensure_ascii=False, indent=2),
        )
        claude = get_claude_client()
        parsed = await claude.complete_json(prompt)
        return MatchResult(
            score=float(parsed.get("score", 0.0)),
            breakdown=parsed.get("breakdown", {}),
            rationale=parsed.get("rationale", ""),
            matched_skills=parsed.get("matched_skills", []),
            missing_skills=parsed.get("missing_skills", []),
        )
    except Exception as exc:
        logger.warning(f"Semantic matching failed, falling back to heuristic: {exc}")
        return None


async def score_match(candidate: Candidate, job: Job, *, use_llm: bool = True) -> MatchResult:
    settings = get_settings()
    if use_llm and settings.anthropic_api_key:
        result = await semantic_score(candidate, job)
        if result is not None:
            return result
    return heuristic_score(candidate, job)


def is_match(result: MatchResult) -> bool:
    settings = get_settings()
    return result.score >= settings.match_threshold_percent


async def _semantic_filter_jobs(
    candidate: Candidate, jobs: list[Job]
) -> list[Job]:
    """Shortlist ``jobs`` to the semantic top-K neighbours of ``candidate``.

    Falls back to the full list when the vector index is disabled or
    empty, so the caller's behaviour is identical in both modes.
    """
    if not vector_index.is_enabled() or not jobs:
        return jobs
    hits = await vector_index.search_jobs_for_candidate(candidate)
    if not hits:
        return jobs
    by_id = {j.id: j for j in jobs}
    # Preserve Qdrant's ordering so the highest-similarity jobs are
    # scored first — relevant if we ever cap downstream calls.
    ordered = [by_id[hid] for hid, _ in hits if hid in by_id]
    if not ordered:
        return jobs
    return ordered


async def _semantic_filter_candidates(
    job: Job, candidates: list[Candidate]
) -> list[Candidate]:
    if not vector_index.is_enabled() or not candidates:
        return candidates
    hits = await vector_index.search_candidates_for_job(job)
    if not hits:
        return candidates
    by_id = {c.id: c for c in candidates}
    ordered = [by_id[hid] for hid, _ in hits if hid in by_id]
    if not ordered:
        return candidates
    return ordered


async def find_matches_for_candidate(
    candidate: Candidate, jobs: list[Job]
) -> list[tuple[Job, MatchResult]]:
    shortlist = await _semantic_filter_jobs(candidate, jobs)
    out = []
    for job in shortlist:
        result = await score_match(candidate, job)
        out.append((job, result))
    out.sort(key=lambda x: x[1].score, reverse=True)
    return out


async def find_matches_for_job(
    job: Job, candidates: list[Candidate]
) -> list[tuple[Candidate, MatchResult]]:
    shortlist = await _semantic_filter_candidates(job, candidates)
    out = []
    for candidate in shortlist:
        result = await score_match(candidate, job)
        out.append((candidate, result))
    out.sort(key=lambda x: x[1].score, reverse=True)
    return out


def to_dict(result: MatchResult) -> dict[str, Any]:
    return {
        "score": result.score,
        "breakdown": result.breakdown,
        "rationale": result.rationale,
        "matched_skills": result.matched_skills,
        "missing_skills": result.missing_skills,
    }
