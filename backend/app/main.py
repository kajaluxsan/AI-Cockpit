"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import (
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
    webhooks,
)
from app.config import get_settings
from app.workers.email_poller import EmailPoller
from app.workers.linkedin_poller import LinkedInPoller

settings = get_settings()

_background_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} ({settings.app_env})")

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

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(candidates.router, prefix="/api/candidates", tags=["candidates"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(calls.router, prefix="/api/calls", tags=["calls"])
app.include_router(emails.router, prefix="/api/emails", tags=["emails"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])


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
