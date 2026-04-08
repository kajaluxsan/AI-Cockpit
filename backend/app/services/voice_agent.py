"""Voice agent: Twilio + Deepgram + ElevenLabs + Claude.

The high-level flow:
1. `initiate_call` triggers an outbound Twilio call. Twilio dials the candidate
   and on connect requests TwiML from `/api/webhooks/twilio/voice`.
2. The TwiML opens a bidirectional Media Stream WebSocket back to this server.
3. Inside `voice_websocket_handler` we:
   - Stream caller audio to Deepgram (STT, with language detection).
   - Send transcripts to Claude using `VOICE_CONVERSATION_PROMPT`.
   - Convert Claude's reply to audio with ElevenLabs.
   - Stream the audio bytes back into the Twilio Media Stream.
4. After the call hangs up, `summarize_call` produces a recruiter-facing summary.

The implementation here is intentionally focused: it provides a working
scaffold and clean integration points so individual providers can be swapped or
mocked. It avoids bringing in heavy real-time dependencies that aren't strictly
required for the demo / dev environment.
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.config import get_settings
from app.models.candidate import Candidate
from app.models.job import Job
from app.services.claude_client import get_claude_client
from app.services.language_detector import detect_language
from app.utils.prompts import CALL_SUMMARY_PROMPT, VOICE_CONVERSATION_PROMPT


# ---------------------------------------------------------------------------
# Twilio outbound call
# ---------------------------------------------------------------------------
def get_twilio_client():
    from twilio.rest import Client

    settings = get_settings()
    if not (settings.twilio_account_sid and settings.twilio_auth_token):
        raise RuntimeError("Twilio is not configured")
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def initiate_call(
    *,
    to_number: str,
    candidate_id: int,
    match_id: int | None = None,
    objective: str | None = None,
) -> dict[str, Any]:
    """Place an outbound call. Returns Twilio Call resource info.

    ``objective`` is an optional free-text instruction (e.g. "Frag nach
    Gehaltsvorstellung und Verfügbarkeit"). It is forwarded to the voice
    handler via a query parameter so the live conversation prompt can pick
    it up.
    """
    from urllib.parse import quote_plus

    settings = get_settings()
    client = get_twilio_client()
    base = (settings.twilio_webhook_base_url or "").rstrip("/")
    voice_url = f"{base}/api/webhooks/twilio/voice?candidate_id={candidate_id}"
    if match_id:
        voice_url += f"&match_id={match_id}"
    if objective:
        voice_url += f"&objective={quote_plus(objective[:500])}"

    call = client.calls.create(
        to=to_number,
        from_=settings.twilio_phone_number,
        url=voice_url,
        status_callback=(
            settings.twilio_status_callback_url
            or f"{base}/api/webhooks/twilio/status"
        ),
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        status_callback_method="POST",
    )
    logger.info(f"Twilio call initiated: SID={call.sid} to={to_number}")
    return {
        "sid": call.sid,
        "to": to_number,
        "from": settings.twilio_phone_number,
        "status": call.status,
    }


# ---------------------------------------------------------------------------
# TwiML generation for incoming voice webhook
# ---------------------------------------------------------------------------
def generate_voice_twiml(
    *,
    candidate_id: int,
    match_id: int | None = None,
    objective: str | None = None,
) -> str:
    from xml.sax.saxutils import escape

    settings = get_settings()
    base = (settings.twilio_webhook_base_url or "").rstrip("/")
    # Replace https/http with wss/ws for the WebSocket URL
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_base}/api/webhooks/twilio/stream"

    params = f'<Parameter name="candidate_id" value="{candidate_id}" />'
    if match_id:
        params += f'<Parameter name="match_id" value="{match_id}" />'
    if objective:
        safe_obj = escape(objective[:500], {'"': "&quot;"})
        params += f'<Parameter name="objective" value="{safe_obj}" />'

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{stream_url}">
      {params}
    </Stream>
  </Connect>
</Response>"""


# ---------------------------------------------------------------------------
# ElevenLabs TTS
# ---------------------------------------------------------------------------
def _voice_id_for_language(settings, language: str) -> str | None:
    """Pick the ElevenLabs voice id for the caller's language.

    Order of preference:
      de → DE voice → EN voice
      en → EN voice → DE voice
      fr → FR voice → EN voice → DE voice
      it → IT voice → EN voice → DE voice

    This means a minimally configured deployment (just DE + EN) still has
    a voice for every caller — the agent might sound slightly accented
    but won't fall silent.
    """
    de = settings.elevenlabs_voice_id_de
    en = settings.elevenlabs_voice_id_en
    fr = settings.elevenlabs_voice_id_fr
    it = settings.elevenlabs_voice_id_it
    if language == "de":
        return de or en
    if language == "en":
        return en or de
    if language == "fr":
        return fr or en or de
    if language == "it":
        return it or en or de
    return de or en


async def synthesize_speech(text: str, language: str = "de") -> bytes:
    """Convert text to PCM audio bytes via ElevenLabs."""
    import httpx

    settings = get_settings()
    if not settings.elevenlabs_api_key:
        logger.warning("ElevenLabs API key not configured")
        return b""

    # Pick the per-language voice, falling back through a sensible chain so
    # that a partially configured deployment (e.g. only DE and EN voices
    # provisioned) still produces audio for FR/IT callers instead of a
    # silent stream.
    voice_id = _voice_id_for_language(settings, language)
    if not voice_id:
        logger.warning(f"No ElevenLabs voice id configured for language={language}")
        return b""

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": settings.elevenlabs_model_id,
        "voice_settings": {
            "stability": settings.elevenlabs_stability,
            "similarity_boost": settings.elevenlabs_similarity_boost,
        },
        "output_format": "ulaw_8000",  # Twilio Media Streams use mulaw 8kHz
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content
    except Exception as exc:
        logger.exception(f"ElevenLabs TTS failed: {exc}")
        return b""


# ---------------------------------------------------------------------------
# Deepgram STT (live, prerecorded fallback)
# ---------------------------------------------------------------------------
async def transcribe_audio_chunks(
    audio_bytes: bytes, *, sample_rate: int = 8000, language_detect: bool = True
) -> tuple[str, str | None]:
    """Transcribe a chunk of audio. Returns (transcript, detected_lang)."""
    settings = get_settings()
    if not settings.deepgram_api_key:
        return "", None
    try:
        from deepgram import DeepgramClient, PrerecordedOptions

        dg = DeepgramClient(settings.deepgram_api_key)
        options = PrerecordedOptions(
            model=settings.deepgram_model,
            detect_language=language_detect,
            encoding="mulaw",
            sample_rate=sample_rate,
        )
        # Run blocking SDK call in executor — it's a small chunk so OK
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: dg.listen.prerecorded.v("1").transcribe_file(
                {"buffer": audio_bytes, "mimetype": "audio/mulaw"}, options
            ),
        )
        results = result.results
        channels = results.channels if hasattr(results, "channels") else []
        transcript = ""
        detected = None
        if channels:
            alt = channels[0].alternatives[0]
            transcript = alt.transcript
            detected = getattr(channels[0], "detected_language", None)
        return transcript, detected
    except Exception as exc:
        logger.exception(f"Deepgram transcription failed: {exc}")
        return "", None


# ---------------------------------------------------------------------------
# Conversation state machine for one call
# ---------------------------------------------------------------------------
@dataclass
class CallSession:
    candidate: Candidate | None
    job: Job | None
    language: str = "de"
    # Optional free-text instruction from the AI chat tool call. When set,
    # it is injected into the voice system prompt so the agent pursues that
    # concrete objective during the call instead of the default job-pitch.
    objective: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    transcript_segments: list[dict[str, Any]] = field(default_factory=list)
    audio_buffer: bytearray = field(default_factory=bytearray)


def build_system_prompt(
    candidate: Candidate | None,
    job: Job | None,
    language: str,
    objective: str | None = None,
) -> str:
    settings = get_settings()
    language_label = {
        "de": "Deutsch (Schweiz)",
        "en": "English",
        "fr": "Français",
        "it": "Italiano",
    }.get(language, "Deutsch (Schweiz)")
    if candidate:
        candidate_profile = (
            f"Name: {candidate.full_name}\n"
            f"Skills: {candidate.skills}\n"
            f"Erfahrung: {candidate.experience_years} Jahre\n"
            f"Standort: {candidate.location}\n"
            f"Verfügbarkeit: {candidate.availability}\n"
        )
        candidate_name = candidate.full_name or (
            "der Kandidat" if language == "de" else "the candidate"
        )
    else:
        candidate_profile = "(unbekannt)"
        candidate_name = "der Kandidat" if language == "de" else "the candidate"
    prompt = VOICE_CONVERSATION_PROMPT.format(
        agent_name=settings.agent_name,
        company_name=settings.company_name,
        candidate_name=candidate_name,
        job_title=job.title if job else "—",
        job_company=(job.company if job else "—") or "—",
        job_location=(job.location if job else "—") or "—",
        job_description=(job.description if job else "—") or "—",
        candidate_profile=candidate_profile,
        language_label=language_label,
    )
    if objective:
        # Append as an explicit, high-priority instruction so the agent
        # opens with / circles back to the recruiter's specific ask.
        prompt += (
            "\n\nZUSÄTZLICHER AUFTRAG VOM RECRUITER (höchste Priorität):\n"
            f"→ {objective}\n"
            "Achte darauf, dieses Anliegen im Gespräch aktiv zu klären, "
            "bevor du das Gespräch beendest."
        )
    return prompt


async def generate_agent_reply(session: CallSession, user_text: str) -> str:
    claude = get_claude_client()
    system = build_system_prompt(
        session.candidate, session.job, session.language, session.objective
    )
    reply = await claude.conversation_turn(
        system=system,
        history=session.history,
        user_message=user_text,
    )
    session.history.append({"role": "user", "content": user_text})
    session.history.append({"role": "assistant", "content": reply})
    return reply


async def opening_line(language: str | None = None) -> str:
    """Multilingual opener until language is detected."""
    settings = get_settings()
    if language == "de":
        return (
            f"Grüezi, mein Name ist {settings.agent_name} von {settings.company_name}. "
            "Ich rufe an wegen einer offenen Stelle. Passt es Ihnen gerade kurz?"
        )
    if language == "en":
        return (
            f"Hello, this is {settings.agent_name} from {settings.company_name}. "
            "I'm calling about an open position. Is now a good time to talk?"
        )
    if language == "fr":
        return (
            f"Bonjour, je suis {settings.agent_name} de {settings.company_name}. "
            "Je vous appelle au sujet d'un poste ouvert. Est-ce que c'est un "
            "bon moment pour discuter ?"
        )
    if language == "it":
        return (
            f"Buongiorno, sono {settings.agent_name} di {settings.company_name}. "
            "La chiamo per una posizione aperta. È un buon momento per parlare?"
        )
    # Default: quadrilingual greeting so the caller can pick
    return (
        f"Grüezi, bonjour, hello, buongiorno — mein Name ist "
        f"{settings.agent_name} von {settings.company_name}. "
        "In welcher Sprache möchten Sie weiterfahren? "
        "Quelle langue préférez-vous ? Which language would you prefer?"
    )


# ---------------------------------------------------------------------------
# Twilio Media Stream WebSocket handler
# ---------------------------------------------------------------------------
async def handle_media_stream(websocket, *, get_session_for_candidate) -> None:
    """Process a Twilio Media Stream WebSocket connection.

    `get_session_for_candidate` is an async callable taking the parsed
    candidate id (from custom parameters) and returning a CallSession.
    """
    session: CallSession | None = None
    stream_sid: str | None = None
    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                stream_sid = data["start"]["streamSid"]
                params = data["start"].get("customParameters", {})
                candidate_id = int(params.get("candidate_id", 0))
                match_id = params.get("match_id")
                objective = params.get("objective") or None
                session = await get_session_for_candidate(
                    candidate_id,
                    int(match_id) if match_id else None,
                    objective,
                )
                opener = await opening_line(None)
                audio = await synthesize_speech(opener, language=session.language)
                if audio:
                    await _send_audio(websocket, stream_sid, audio)

            elif event == "media" and session is not None:
                payload = data["media"]["payload"]
                chunk = base64.b64decode(payload)
                session.audio_buffer.extend(chunk)
                # Process roughly every ~2s of audio (8kHz mulaw -> 16000 bytes)
                if len(session.audio_buffer) >= 16000:
                    audio = bytes(session.audio_buffer)
                    session.audio_buffer.clear()
                    transcript, detected = await transcribe_audio_chunks(audio)
                    if transcript:
                        if detected and detected != session.language:
                            for code in ("de", "en", "fr", "it"):
                                if detected.startswith(code):
                                    session.language = code
                                    break
                        session.transcript_segments.append(
                            {"role": "user", "text": transcript}
                        )
                        reply = await generate_agent_reply(session, transcript)
                        session.transcript_segments.append(
                            {"role": "assistant", "text": reply}
                        )
                        speech = await synthesize_speech(reply, language=session.language)
                        if speech and stream_sid:
                            await _send_audio(websocket, stream_sid, speech)

            elif event == "stop":
                logger.info(f"Twilio media stream stopped: {stream_sid}")
                break
    except Exception as exc:
        logger.exception(f"Media stream handler error: {exc}")


async def _send_audio(websocket, stream_sid: str, audio: bytes) -> None:
    payload = base64.b64encode(audio).decode()
    await websocket.send_text(
        json.dumps(
            {
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": payload},
            }
        )
    )


# ---------------------------------------------------------------------------
# Post-call summarization
# ---------------------------------------------------------------------------
async def summarize_call(transcript_segments: list[dict[str, Any]]) -> dict[str, Any]:
    text_lines = []
    for seg in transcript_segments:
        role = "Kandidat" if seg.get("role") == "user" else "Agent"
        text_lines.append(f"{role}: {seg.get('text', '')}")
    transcript_text = "\n".join(text_lines)
    if not transcript_text.strip():
        return {
            "summary": "",
            "interest_level": None,
            "key_points": [],
            "concerns": [],
            "next_steps": "",
            "follow_up_needed": False,
        }
    try:
        claude = get_claude_client()
        return await claude.complete_json(
            CALL_SUMMARY_PROMPT.format(transcript=transcript_text)
        )
    except Exception as exc:
        logger.exception(f"Call summarization failed: {exc}")
        return {
            "summary": "Automatische Zusammenfassung fehlgeschlagen.",
            "interest_level": None,
            "key_points": [],
            "concerns": [],
            "next_steps": "",
            "follow_up_needed": False,
        }


# Re-export for the language detector helper
__all__ = [
    "initiate_call",
    "generate_voice_twiml",
    "synthesize_speech",
    "transcribe_audio_chunks",
    "handle_media_stream",
    "summarize_call",
    "CallSession",
    "detect_language",
]
