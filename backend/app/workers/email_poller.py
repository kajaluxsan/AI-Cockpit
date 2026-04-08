"""Periodic email poller worker.

Responsibility:
- Pull unseen messages from IMAP / Graph API.
- Extract attachments and parse CV text via Claude.
- Upsert the candidate through the CRM layer (dedupe by email).
- Append the message to the candidate protocol (EmailLog).
- Trigger follow-up mail if required CRM fields are missing.
- Kick off matching for brand-new candidates.
"""

from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models.candidate import CandidateSource, CandidateStatus
from app.models.email_log import EmailDirection, EmailKind, EmailLog
from app.services import crm, cv_parser
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

            # Combine email body + attachment text for parsing. Keep track of
            # the "primary" CV attachment bytes so we can persist the file and
            # serve it back as a PDF preview.
            attachment_text = ""
            cv_bytes: bytes | None = None
            cv_filename: str | None = None
            for att in em.attachments:
                text = cv_parser.extract_text_from_attachment(att.filename, att.data)
                if text:
                    attachment_text += "\n\n" + text
                    if cv_bytes is None:
                        cv_bytes = att.data
                        cv_filename = att.filename

            full_text = (em.body_plain or "") + attachment_text
            parsed = await cv_parser.parse_cv_text(full_text) if full_text.strip() else {}

            # Upsert via CRM (dedupe by email)
            result = await crm.upsert_from_inbound(
                db,
                parsed=parsed or {},
                cv_text=full_text if full_text.strip() else None,
                cv_filename=cv_filename,
                cv_bytes=cv_bytes,
                source=CandidateSource.EMAIL,
                source_reference=em.message_id or em.from_address,
                fallback_email=em.from_address,
                fallback_name=em.from_name or None,
            )
            candidate = result.candidate

            # Always append the inbound mail to the protocol
            await crm.append_message(
                db,
                candidate=candidate,
                direction=EmailDirection.INBOUND,
                kind=EmailKind.APPLICATION if result.created else EmailKind.REPLY,
                from_address=em.from_address,
                to_address=em.to_address,
                subject=em.subject,
                body=em.body_plain,
                message_id=em.message_id,
                attachments_count=len(em.attachments),
            )
            await db.commit()
            await db.refresh(candidate)

            # Auto follow-up for missing CRM required fields
            if (
                result.missing_required
                and self.settings.match_auto_email_followup
                and candidate.email
            ):
                mail = await send_followup_email(candidate, result.missing_required)
                if mail:
                    await crm.append_message(
                        db,
                        candidate=candidate,
                        direction=EmailDirection.OUTBOUND,
                        kind=EmailKind.FOLLOWUP_REQUEST,
                        from_address=self.settings.email_from_address,
                        to_address=candidate.email,
                        subject=mail["subject"],
                        body=mail["body"],
                    )
                    candidate.status = CandidateStatus.INFO_REQUESTED
                    await db.commit()

            # Run matching for brand-new, complete candidates
            if result.created and not result.missing_required:
                try:
                    await process_new_candidate(db, candidate)
                except Exception as exc:
                    logger.exception(f"Match processing failed: {exc}")
