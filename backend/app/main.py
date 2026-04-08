"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import (
    auth as auth_api,
    calls,
    candidates,
    chat,
    dashboard,
    emails,
    events,
    jobs,
    matches,
    messages,
    settings as settings_api,
    templates as templates_api,
    reports as reports_api,
    webhooks,
)
from app.config import get_settings
from app.database import SessionLocal
from app.services.auth import bootstrap_admin_if_needed, current_user_dep
from app.workers.email_poller import EmailPoller
from app.workers.gdpr_purge import GDPRPurgeWorker
from app.workers.linkedin_poller import LinkedInPoller

settings = get_settings()

_background_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} ({settings.app_env})")

    # --- Auth bootstrap -------------------------------------------------
    # If AUTH_BOOTSTRAP_ADMIN_* env vars are set and the users table is
    # empty, create the initial admin so the recruiter can log in the
    # first time without running a manual SQL insert.
    try:
        async with SessionLocal() as db:
            await bootstrap_admin_if_needed(db)
    except Exception as exc:
        # Don't crash the app if bootstrap fails (e.g. DB not yet ready) —
        # the recruiter can still create users via the admin API later.
        logger.error(f"Auth bootstrap failed: {exc}")

    if settings.auth_jwt_secret == "change-me-jwt-secret":
        logger.warning(
            "AUTH_JWT_SECRET is still the default placeholder. "
            "Override it in .env before shipping — sessions are otherwise forgeable."
        )

    if settings.source_email_enabled:
        poller = EmailPoller()
        task = asyncio.create_task(poller.run_forever())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.info("Email poller started")
    else:
        logger.info("Email source disabled")

    if settings.source_linkedin_enabled:
        linkedin_poller = LinkedInPoller()
        task = asyncio.create_task(linkedin_poller.run_forever())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.info("LinkedIn poller started")
    else:
        logger.info("LinkedIn source disabled")

    if settings.source_external_api_enabled:
        logger.info("External API source enabled")
    else:
        logger.info("External API source disabled")

    # GDPR retention purge — always scheduled; worker decides internally
    # whether to run based on GDPR_RETENTION_DAYS.
    gdpr_worker = GDPRPurgeWorker()
    task = asyncio.create_task(gdpr_worker.run_forever())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    logger.info("GDPR purge worker scheduled")

    yield

    logger.info("Shutting down background tasks")
    for task in list(_background_tasks):
        task.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)


app = FastAPI(
    title=settings.app_name,
    description="AI Recruiting Telephone Agent for Swiss recruiting agencies",
    version="0.1.0",
    lifespan=lifespan,
    debug=settings.app_debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public routers: /auth is self-describing (login can't require auth),
# /webhooks is protected by a shared-secret header, not a session cookie.
app.include_router(auth_api.router, prefix="/api/auth", tags=["auth"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])

# Session-protected routers. Attaching ``current_user_dep`` at include-time
# means every handler inside the router inherits the auth check — we don't
# have to remember to add ``Depends(current_user_dep)`` to each individual
# endpoint. Any unauthenticated request gets a 401 before the handler runs.
_auth_deps = [Depends(current_user_dep)]
app.include_router(
    dashboard.router, prefix="/api/dashboard", tags=["dashboard"], dependencies=_auth_deps
)
app.include_router(
    candidates.router, prefix="/api/candidates", tags=["candidates"], dependencies=_auth_deps
)
app.include_router(
    jobs.router, prefix="/api/jobs", tags=["jobs"], dependencies=_auth_deps
)
app.include_router(
    matches.router, prefix="/api/matches", tags=["matches"], dependencies=_auth_deps
)
app.include_router(
    calls.router, prefix="/api/calls", tags=["calls"], dependencies=_auth_deps
)
app.include_router(
    emails.router, prefix="/api/emails", tags=["emails"], dependencies=_auth_deps
)
app.include_router(
    messages.router, prefix="/api/messages", tags=["messages"], dependencies=_auth_deps
)
app.include_router(
    chat.router, prefix="/api/chat", tags=["chat"], dependencies=_auth_deps
)
app.include_router(
    events.router, prefix="/api/events", tags=["events"], dependencies=_auth_deps
)
app.include_router(
    settings_api.router, prefix="/api/settings", tags=["settings"], dependencies=_auth_deps
)
app.include_router(
    templates_api.router, prefix="/api/templates", tags=["templates"], dependencies=_auth_deps
)
app.include_router(
    reports_api.router, prefix="/api/reports", tags=["reports"], dependencies=_auth_deps
)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "env": settings.app_env,
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
