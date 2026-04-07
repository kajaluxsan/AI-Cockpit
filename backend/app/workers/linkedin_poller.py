"""Periodic LinkedIn poller worker."""

from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models.candidate import Candidate, CandidateSource, CandidateStatus
from app.models.job import Job, JobSource, JobStatus
from app.services.linkedin_service import get_linkedin_service
from app.workers.match_processor import process_new_candidate


class LinkedInPoller:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run_forever(self) -> None:
        if not self.settings.source_linkedin_enabled:
            logger.info("LinkedIn poller: source disabled, exiting")
            return
        interval = max(60, self.settings.linkedin_poll_interval_seconds)
        logger.info(f"LinkedIn poller: polling every {interval}s")
        while True:
            try:
                await self.poll_once()
            except Exception as exc:
                logger.exception(f"LinkedIn poller iteration failed: {exc}")
            await asyncio.sleep(interval)

    async def poll_once(self) -> None:
        service = get_linkedin_service()
        postings = await service.fetch_job_postings()
        async with SessionLocal() as db:
            for posting in postings:
                exists = (
                    await db.execute(
                        select(Job).where(
                            Job.source == JobSource.LINKEDIN,
                            Job.source_reference == posting.external_id,
                        )
                    )
                ).scalar_one_or_none()
                if not exists:
                    db.add(
                        Job(
                            title=posting.title,
                            company=posting.company,
                            location=posting.location,
                            description=posting.description,
                            source=JobSource.LINKEDIN,
                            source_reference=posting.external_id,
                            status=JobStatus.OPEN,
                        )
                    )
            await db.commit()

            for posting in postings:
                applicants = await service.fetch_applicants(posting.external_id)
                for app in applicants:
                    cand_exists = (
                        await db.execute(
                            select(Candidate).where(
                                Candidate.source == CandidateSource.LINKEDIN,
                                Candidate.source_reference == app.external_id,
                            )
                        )
                    ).scalar_one_or_none()
                    if cand_exists:
                        continue
                    candidate = Candidate(
                        full_name=app.full_name,
                        email=app.email,
                        headline=app.headline,
                        source=CandidateSource.LINKEDIN,
                        source_reference=app.external_id,
                        status=CandidateStatus.NEW,
                    )
                    db.add(candidate)
                    await db.commit()
                    await db.refresh(candidate)
                    try:
                        await process_new_candidate(db, candidate)
                    except Exception as exc:
                        logger.exception(f"LinkedIn match processing failed: {exc}")
