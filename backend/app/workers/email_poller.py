"""Periodic email poller worker."""

from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models.candidate import Candidate, CandidateSource, CandidateStatus
from app.models.email_log import EmailDirection, EmailKind, EmailLog
from app.services import cv_parser
from app.services.email_service import IncomingEmail, get_email_service
from app.services.followup_mail import send_followup_email
from app.workers.match_processor import process_new_candidate


class EmailPoller:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run_forever(self) -> None:
        if not self.settings.source_email_enabled:
            logger.info("Email poller: source disabled, exiting")
            return
        interval = max(15, self.settings.email_poll_interval_seconds)
        logger.info(f"Email poller: polling every {interval}s")
        while True:
            try:
                await self.poll_once()
            except Exception as exc:
                logger.exception(f"Email poller iteration failed: {exc}")
            await asyncio.sleep(interval)

    async def poll_once(self) -> None:
        service = get_email_service()
        emails = await service.fetch_unseen()
        if not emails:
            return
        logger.info(f"Email poller: {len(emails)} new email(s)")
        for em in emails:
            await self.handle_email(em)

    async def handle_email(self, em: IncomingEmail) -> None:
        async with SessionLocal() as db:
            # Skip duplicates by message id
            if em.message_id:
                existing = (
                    await db.execute(
                        select(EmailLog).where(EmailLog.message_id == em.message_id)
                    )
                ).scalar_one_or_none()
                if existing:
                    return

            # Combine email body + attachment text for parsing
            attachment_text = ""
            for att in em.attachments:
                attachment_text += "\n\n" + cv_parser.extract_text_from_attachment(
                    att.filename, att.data
                )
            full_text = (em.body_plain or "") + attachment_text

            parsed = await cv_parser.parse_cv_text(full_text) if full_text.strip() else {}
            missing = cv_parser.detect_missing_fields(parsed) if parsed else []

            candidate = Candidate(
                full_name=parsed.get("full_name") or em.from_name or em.from_address,
                email=parsed.get("email") or em.from_address,
                phone=parsed.get("phone"),
                location=parsed.get("location"),
                language=parsed.get("language"),
                headline=parsed.get("headline"),
                summary=parsed.get("summary"),
                skills=parsed.get("skills"),
                experience_years=parsed.get("experience_years"),
                education=parsed.get("education"),
                work_history=parsed.get("work_history"),
                salary_expectation=parsed.get("salary_expectation"),
                salary_currency=parsed.get("salary_currency"),
                availability=parsed.get("availability"),
                languages_spoken=parsed.get("languages_spoken"),
                source=CandidateSource.EMAIL,
                source_reference=em.message_id or em.from_address,
                cv_text=full_text[:200000] if full_text else None,
                status=(
                    CandidateStatus.INFO_REQUESTED
                    if missing
                    else CandidateStatus.PARSED
                ),
                missing_fields=missing or None,
            )
            db.add(candidate)

            log = EmailLog(
                direction=EmailDirection.INBOUND,
                kind=EmailKind.APPLICATION,
                message_id=em.message_id,
                from_address=em.from_address,
                to_address=em.to_address,
                subject=em.subject,
                body=em.body_plain[:50000] if em.body_plain else None,
                attachments_count=len(em.attachments),
            )
            db.add(log)
            await db.commit()
            await db.refresh(candidate)
            log.candidate_id = candidate.id
            await db.commit()

            # Auto follow-up for missing fields
            if (
                missing
                and self.settings.match_auto_email_followup
                and candidate.email
            ):
                mail = await send_followup_email(candidate, missing)
                if mail:
                    db.add(
                        EmailLog(
                            candidate_id=candidate.id,
                            direction=EmailDirection.OUTBOUND,
                            kind=EmailKind.FOLLOWUP_REQUEST,
                            from_address=self.settings.email_from_address,
                            to_address=candidate.email,
                            subject=mail["subject"],
                            body=mail["body"],
                        )
                    )
                    await db.commit()

            # Run matching
            try:
                await process_new_candidate(db, candidate)
            except Exception as exc:
                logger.exception(f"Match processing failed: {exc}")
