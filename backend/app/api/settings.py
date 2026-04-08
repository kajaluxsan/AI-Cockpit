"""Settings inspection API.

Most values come from ``.env`` and are read-only here. The few values a
recruiter is allowed to tune at runtime (e.g. the CRM required field set)
live in :mod:`app.services.runtime_config`, which is persisted to a JSON
file inside ``CV_STORAGE_DIR``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.services import runtime_config
from app.services.email_service import send_email

router = APIRouter()


class RuntimeConfigPatch(BaseModel):
    crm_required_fields: list[str] | str | None = None


@router.get("/")
async def get_app_settings():
    s = get_settings()
    return {
        "app": {
            "name": s.app_name,
            "env": s.app_env,
            "agent_name": s.agent_name,
            "company_name": s.company_name,
        },
        "sources": {
            "email": s.source_email_enabled,
            "linkedin": s.source_linkedin_enabled,
            "external_api": s.source_external_api_enabled,
        },
        "matching": {
            "threshold_percent": s.match_threshold_percent,
            "auto_call_enabled": s.match_auto_call_enabled,
            "auto_email_followup": s.match_auto_email_followup,
            "missing_info_fields": s.missing_info_field_list,
        },
        "email": {
            "protocol": s.email_protocol,
            "imap_host": s.email_imap_host,
            "imap_user": s.email_imap_user,
            "smtp_host": s.email_smtp_host,
            "from_address": s.email_from_address,
            "poll_interval": s.email_poll_interval_seconds,
        },
        "twilio": {
            "phone_number": s.twilio_phone_number,
            "configured": bool(s.twilio_account_sid),
        },
        "elevenlabs": {
            "configured": bool(s.elevenlabs_api_key),
            "model": s.elevenlabs_model_id,
        },
        "deepgram": {
            "configured": bool(s.deepgram_api_key),
            "model": s.deepgram_model,
            "language_detect": s.deepgram_language_detect,
        },
        "anthropic": {
            "configured": bool(s.anthropic_api_key),
            "model": s.anthropic_model,
        },
        "external_api": {
            "base_url": s.external_api_base_url,
            "auth_type": s.external_api_auth_type,
        },
    }


@router.post("/test/email")
async def test_email_send(to: str):
    """Send a test email to the given address using configured SMTP."""
    ok = await send_email(
        to_address=to,
        subject="[RecruiterAI] Test email",
        body="If you receive this, your SMTP configuration works.",
    )
    return {"success": ok}


@router.post("/test/twilio")
async def test_twilio():
    s = get_settings()
    return {
        "configured": bool(s.twilio_account_sid and s.twilio_auth_token),
        "phone_number": s.twilio_phone_number,
        "message": "Twilio credentials present" if s.twilio_account_sid else "Twilio not configured",
    }


@router.get("/runtime")
async def get_runtime_config() -> dict[str, Any]:
    """Return the runtime-overridable config (CRM required fields, etc)."""
    return runtime_config.get_all()


@router.put("/runtime")
async def update_runtime_config(patch: RuntimeConfigPatch) -> dict[str, Any]:
    """Update the runtime-overridable config. Currently supports
    ``crm_required_fields``; additional keys will surface validation errors."""
    values = patch.model_dump(exclude_unset=True, exclude_none=True)
    if not values:
        return runtime_config.get_all()
    try:
        return runtime_config.update(values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
