"""AI Chat API (scoped to a candidate).

The recruiter opens a per-candidate chat. Claude is given:
- the candidate profile (CV + CRM fields)
- the protocol (emails + calls)
- a tool spec: ``send_email``, ``initiate_call``

When the model replies with a tool call, the backend executes it and appends
both the user turn and the assistant turn (+ tool result) to the
``chat_messages`` table — so the conversation is persisted across sessions.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.call_log import CallLog, CallStatus
from app.models.candidate import Candidate, CandidateStatus
from app.models.chat_message import ChatMessage, ChatRole
from app.models.email_log import EmailDirection, EmailKind
from app.services import crm
from app.services.claude_client import get_claude_client
from app.services.email_service import send_email
from app.services.event_broker import broker
from app.services.voice_agent import initiate_call as twilio_initiate_call
from app.utils.prompts import CANDIDATE_CHAT_SYSTEM_PROMPT

router = APIRouter()

# ---------------------------------------------------------------------------
# Rate limiter (per-candidate sliding window)
# ---------------------------------------------------------------------------
# The AI chat has two expensive side effects: a Claude call on every turn
# and, on tool-call, an outbound email or an outbound Twilio call. A runaway
# agent loop (or a tab left open overnight) could easily rack up hundreds of
# calls against a single candidate. This sliding-window limiter caps turns
# per candidate per minute. It lives in-memory — good enough for a single
# backend process; swap for Redis if you ever run replicas.
_CHAT_WINDOW_SECONDS = 60
_CHAT_MAX_TURNS = 12
_chat_turns: dict[int, deque[float]] = defaultdict(deque)


def _check_rate_limit(candidate_id: int) -> None:
    """Raise 429 if the chat exceeded ``_CHAT_MAX_TURNS`` per window."""
    now = time.monotonic()
    window = _chat_turns[candidate_id]
    cutoff = now - _CHAT_WINDOW_SECONDS
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= _CHAT_MAX_TURNS:
        retry_in = int(_CHAT_WINDOW_SECONDS - (now - window[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=(
                f"Chat-Rate-Limit erreicht ({_CHAT_MAX_TURNS} Nachrichten / "
                f"{_CHAT_WINDOW_SECONDS}s). Bitte {retry_in}s warten."
            ),
            headers={"Retry-After": str(retry_in)},
        )
    window.append(now)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    role: str
    content: str
    tool_name: str | None
    tool_payload: dict[str, Any] | None
    created_at: datetime


class ChatSendPayload(BaseModel):
    content: str
    auto_execute_tools: bool = True


def _candidate_profile_json(c: Candidate) -> str:
    payload = {
        "id": c.id,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "location": c.location,
        "headline": c.headline,
        "summary": c.summary,
        "skills": c.skills,
        "experience_years": c.experience_years,
        "salary_expectation": c.salary_expectation,
        "salary_currency": c.salary_currency,
        "availability": c.availability,
        "languages_spoken": c.languages_spoken,
        "status": c.status.value if c.status else None,
        "missing_fields": c.missing_fields,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def _build_protocol_snippet(db: AsyncSession, candidate_id: int) -> str:
    """Short, human-readable history for the system prompt."""
    from app.models.email_log import EmailLog  # local import avoids circular

    emails = (
        await db.execute(
            select(EmailLog)
            .where(EmailLog.candidate_id == candidate_id)
            .order_by(EmailLog.created_at.desc())
            .limit(10)
        )
    ).scalars().all()
    calls = (
        await db.execute(
            select(CallLog)
            .where(CallLog.candidate_id == candidate_id)
            .order_by(CallLog.created_at.desc())
            .limit(5)
        )
    ).scalars().all()

    lines: list[str] = []
    for em in emails:
        body = (em.body or "")[:200].replace("\n", " ")
        lines.append(
            f"- [{em.direction.value}] {em.created_at:%Y-%m-%d} "
            f"{em.subject or em.kind.value}: {body}"
        )
    for c in calls:
        summary = (c.summary or c.transcript or "")[:200].replace("\n", " ")
        lines.append(f"- [call] {c.created_at:%Y-%m-%d} {c.status.value}: {summary}")
    if not lines:
        return "(keine bisherige Kommunikation)"
    return "\n".join(lines)


async def _load_history(db: AsyncSession, candidate_id: int) -> list[ChatMessage]:
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.candidate_id == candidate_id)
            .order_by(ChatMessage.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


@router.get("/{candidate_id}", response_model=list[ChatMessageOut])
async def get_chat(candidate_id: int, db: AsyncSession = Depends(get_db)):
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    history = await _load_history(db, candidate_id)
    return [
        ChatMessageOut(
            id=m.id,
            candidate_id=m.candidate_id,
            role=m.role.value,
            content=m.content,
            tool_name=m.tool_name,
            tool_payload=m.tool_payload,
            created_at=m.created_at,
        )
        for m in history
        if m.role != ChatRole.SYSTEM
    ]


@router.post("/{candidate_id}", response_model=list[ChatMessageOut])
async def send_message(
    candidate_id: int,
    payload: ChatSendPayload,
    db: AsyncSession = Depends(get_db),
):
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    _check_rate_limit(candidate_id)

    settings = get_settings()
    protocol = await _build_protocol_snippet(db, candidate_id)
    system_prompt = CANDIDATE_CHAT_SYSTEM_PROMPT.format(
        agent_name=settings.agent_name,
        company_name=settings.company_name,
        candidate_profile=_candidate_profile_json(candidate),
        protocol=protocol,
    )

    # Persist user turn first
    user_msg = ChatMessage(
        candidate_id=candidate_id,
        role=ChatRole.USER,
        content=payload.content,
    )
    db.add(user_msg)
    await db.flush()

    # Build history for Claude — exclude tool rows (those are internal)
    history_rows = await _load_history(db, candidate_id)
    history: list[dict[str, str]] = []
    for m in history_rows:
        if m.role in (ChatRole.SYSTEM, ChatRole.TOOL):
            continue
        history.append({"role": m.role.value, "content": m.content})

    # Call Claude
    assistant_content = "{}"
    parsed: dict[str, Any] = {"action": "none", "message": "(keine Antwort)"}
    if not settings.anthropic_api_key:
        parsed = {
            "action": "none",
            "message": "Claude ist nicht konfiguriert. Setze ANTHROPIC_API_KEY.",
        }
    else:
        try:
            claude = get_claude_client()
            assistant_content = await claude.conversation_turn(
                system=system_prompt,
                history=history[:-1],  # history excluding the turn we just added
                user_message=payload.content,
                temperature=0.3,
                max_tokens=800,
            )
            parsed = _parse_tool_response(assistant_content)
        except Exception as exc:
            logger.exception(f"Claude chat turn failed: {exc}")
            parsed = {
                "action": "none",
                "message": f"Fehler beim Claude-Aufruf: {exc}",
            }

    assistant_msg = ChatMessage(
        candidate_id=candidate_id,
        role=ChatRole.ASSISTANT,
        content=parsed.get("message", ""),
        tool_name=parsed.get("action") if parsed.get("action") != "none" else None,
        tool_payload=parsed.get("args") if parsed.get("action") != "none" else None,
    )
    db.add(assistant_msg)
    await db.flush()

    # Tool execution
    if payload.auto_execute_tools and parsed.get("action") == "send_email":
        args = parsed.get("args") or {}
        tool_note = await _execute_send_email(db, candidate, args)
        db.add(
            ChatMessage(
                candidate_id=candidate_id,
                role=ChatRole.TOOL,
                content=tool_note,
                tool_name="send_email",
                tool_payload=args,
            )
        )
    elif payload.auto_execute_tools and parsed.get("action") == "initiate_call":
        args = parsed.get("args") or {}
        tool_note = await _execute_initiate_call(db, candidate, args)
        db.add(
            ChatMessage(
                candidate_id=candidate_id,
                role=ChatRole.TOOL,
                content=tool_note,
                tool_name="initiate_call",
                tool_payload=args,
            )
        )

    await db.commit()

    # Live-notify open chat dock windows for this candidate
    await broker.publish(
        "chat.append",
        {
            "candidate_id": candidate_id,
            "action": parsed.get("action"),
        },
    )

    rows = await _load_history(db, candidate_id)
    return [
        ChatMessageOut(
            id=m.id,
            candidate_id=m.candidate_id,
            role=m.role.value,
            content=m.content,
            tool_name=m.tool_name,
            tool_payload=m.tool_payload,
            created_at=m.created_at,
        )
        for m in rows
        if m.role != ChatRole.SYSTEM
    ]


def _parse_tool_response(raw: str) -> dict[str, Any]:
    """Accept either a strict JSON object or plain text (treated as a message)."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "action" in obj:
            obj.setdefault("message", "")
            return obj
    except json.JSONDecodeError:
        pass
    return {"action": "none", "message": raw.strip()}


async def _execute_send_email(
    db: AsyncSession, candidate: Candidate, args: dict[str, Any]
) -> str:
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not candidate.email:
        return "Fehlgeschlagen: Kandidat hat keine E-Mail-Adresse."
    if not subject or not body:
        return "Fehlgeschlagen: subject oder body fehlen."
    ok = await send_email(to_address=candidate.email, subject=subject, body=body)
    if not ok:
        return "Fehlgeschlagen: SMTP nicht konfiguriert oder Versand fehlgeschlagen."
    await crm.append_message(
        db,
        candidate=candidate,
        direction=EmailDirection.OUTBOUND,
        kind=EmailKind.OTHER,
        from_address=get_settings().email_from_address,
        to_address=candidate.email,
        subject=subject,
        body=body,
    )
    candidate.status = CandidateStatus.CONTACTED
    return f"E-Mail an {candidate.email} gesendet: {subject}"


async def _execute_initiate_call(
    db: AsyncSession, candidate: Candidate, args: dict[str, Any]
) -> str:
    if not candidate.phone:
        return "Fehlgeschlagen: Kandidat hat keine Telefonnummer."
    reason = (args.get("reason") or "").strip()
    try:
        info = twilio_initiate_call(
            to_number=candidate.phone,
            candidate_id=candidate.id,
            objective=reason or None,
        )
    except Exception as exc:
        return f"Fehlgeschlagen: Twilio-Fehler: {exc}"

    log = CallLog(
        candidate_id=candidate.id,
        twilio_call_sid=info.get("sid"),
        from_number=info.get("from"),
        to_number=info.get("to"),
        status=CallStatus.INITIATED,
        # Persist what the recruiter (via the AI chat) actually wanted to ask
        # — surfaces in the call protocol so the recruiter can verify the AI
        # raised the right topics on the call.
        summary=(f"Auftrag aus AI-Chat: {reason}" if reason else None),
    )
    db.add(log)
    return f"Anruf initiiert an {candidate.phone}. Grund: {reason or '—'}"
