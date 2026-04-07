"""Matching pipeline triggered when a new candidate appears."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.candidate import Candidate, CandidateStatus
from app.models.call_log import CallLog, CallStatus
from app.models.job import Job, JobStatus
from app.models.match import Match, MatchStatus
from app.services import matching_engine, voice_agent
from app.services.notification import notify_recruiter_match


async def process_new_candidate(db: AsyncSession, candidate: Candidate) -> list[Match]:
    settings = get_settings()
    open_jobs = (
        await db.execute(select(Job).where(Job.status == JobStatus.OPEN))
    ).scalars().all()
    if not open_jobs:
        return []

    created: list[Match] = []
    for job in open_jobs:
        result = await matching_engine.score_match(candidate, job)
        match = Match(
            candidate_id=candidate.id,
            job_id=job.id,
            score=result.score,
            score_breakdown=matching_engine.to_dict(result),
            rationale=result.rationale,
            status=MatchStatus.NEW,
        )
        db.add(match)
        created.append(match)

        if matching_engine.is_match(result):
            candidate.status = CandidateStatus.MATCHED
            await notify_recruiter_match(candidate, job, result.score, result.rationale)

            if (
                settings.match_auto_call_enabled
                and candidate.phone
                and settings.twilio_account_sid
            ):
                try:
                    twilio_info = voice_agent.initiate_call(
                        to_number=candidate.phone,
                        candidate_id=candidate.id,
                        match_id=None,  # match.id known after commit
                    )
                    db.add(
                        CallLog(
                            candidate_id=candidate.id,
                            twilio_call_sid=twilio_info["sid"],
                            from_number=twilio_info["from"],
                            to_number=twilio_info["to"],
                            status=CallStatus.INITIATED,
                            detected_language=candidate.language,
                        )
                    )
                    candidate.status = CandidateStatus.CONTACTED
                except Exception as exc:
                    logger.warning(f"Auto-call failed: {exc}")

    await db.commit()
    return created
