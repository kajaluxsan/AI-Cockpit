"""Background worker that enforces the GDPR / FADP retention window.

Runs once per ``GDPR_PURGE_INTERVAL_MINUTES`` (default: daily) and calls
:func:`app.services.gdpr.purge_expired_candidates`. Set
``GDPR_RETENTION_DAYS=0`` to turn the worker off without having to
remove its task from main.py.

The worker is deliberately conservative: it only anonymises candidates
that are *already* in the REJECTED state (or that have an explicit
``retain_until`` set in the past). Active candidates, placed candidates
and candidates still being matched are never touched, no matter how old
the record is.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from app.config import get_settings
from app.database import SessionLocal
from app.services.gdpr import purge_expired_candidates


class GDPRPurgeWorker:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run_forever(self) -> None:
        days = self.settings.gdpr_retention_days
        if days <= 0:
            logger.info("GDPR purge worker: disabled (GDPR_RETENTION_DAYS=0)")
            return
        interval_seconds = max(60, self.settings.gdpr_purge_interval_minutes * 60)
        logger.info(
            f"GDPR purge worker: running every {interval_seconds}s, "
            f"retention={days} days"
        )
        while True:
            try:
                await self._run_once()
            except Exception as exc:
                logger.exception(f"GDPR purge iteration failed: {exc}")
            await asyncio.sleep(interval_seconds)

    async def _run_once(self) -> None:
        async with SessionLocal() as db:
            count = await purge_expired_candidates(db)
            if count:
                logger.info(f"GDPR purge: anonymised {count} candidate(s)")
            else:
                logger.debug("GDPR purge: nothing to do")
