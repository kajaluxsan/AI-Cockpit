"""Email service: IMAP polling, parsing, attachments, SMTP send.

Supports two protocols configurable via EMAIL_PROTOCOL:
- imap (default — Outlook/Exchange/any IMAP)
- graph_api (Microsoft Graph API)
"""

from __future__ import annotations

import email
from dataclasses import dataclass, field
from email.header import decode_header
from email.message import EmailMessage as StdEmailMessage
from email.utils import parseaddr
from typing import Any

import aiosmtplib
import httpx
from loguru import logger

from app.config import get_settings


@dataclass
class IncomingAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class IncomingEmail:
    message_id: str
    from_address: str
    from_name: str
    to_address: str
    subject: str
    body_plain: str
    body_html: str | None = None
    attachments: list[IncomingAttachment] = field(default_factory=list)


def _decode(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return value.decode("latin-1", errors="replace")
    parts = decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _parse_email_message(raw: bytes) -> IncomingEmail:
    msg = email.message_from_bytes(raw)
    message_id = _decode(msg.get("Message-ID")) or ""
    subject = _decode(msg.get("Subject"))
    from_raw = _decode(msg.get("From"))
    to_raw = _decode(msg.get("To"))
    from_name, from_addr = parseaddr(from_raw)
    _, to_addr = parseaddr(to_raw)

    body_plain = ""
    body_html: str | None = None
    attachments: list[IncomingAttachment] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp or part.get_filename():
                fname = _decode(part.get_filename()) or "attachment.bin"
                payload = part.get_payload(decode=True) or b""
                attachments.append(
                    IncomingAttachment(
                        filename=fname, content_type=ctype, data=payload
                    )
                )
            elif ctype == "text/plain" and not body_plain:
                payload = part.get_payload(decode=True) or b""
                body_plain = payload.decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
            elif ctype == "text/html" and not body_html:
                payload = part.get_payload(decode=True) or b""
                body_html = payload.decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
    else:
        payload = msg.get_payload(decode=True) or b""
        body_plain = payload.decode(
            msg.get_content_charset() or "utf-8", errors="replace"
        )

    return IncomingEmail(
        message_id=message_id,
        from_address=from_addr,
        from_name=from_name,
        to_address=to_addr,
        subject=subject,
        body_plain=body_plain,
        body_html=body_html,
        attachments=attachments,
    )


# ---------------------------------------------------------------------------
# IMAP implementation (using aioimaplib)
# ---------------------------------------------------------------------------
class ImapEmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def fetch_unseen(self) -> list[IncomingEmail]:
        from aioimaplib import aioimaplib

        host = self.settings.email_imap_host
        port = self.settings.email_imap_port
        user = self.settings.email_imap_user
        password = self.settings.email_imap_password
        if not (host and user):
            logger.warning("IMAP not configured, skipping fetch")
            return []

        client = aioimaplib.IMAP4_SSL(host=host, port=port)
        try:
            await client.wait_hello_from_server()
            await client.login(user, password or "")
            await client.select(self.settings.email_inbox_folder)

            status, data = await client.search("UNSEEN")
            if status != "OK" or not data:
                return []

            ids = data[0].split()
            results: list[IncomingEmail] = []
            for msg_id in ids:
                fetch_status, fetch_data = await client.fetch(
                    msg_id.decode(), "(RFC822)"
                )
                if fetch_status != "OK":
                    continue
                # Response format: [b'1 (RFC822 {1234}', b'<raw bytes>', b')']
                raw_bytes = b""
                for chunk in fetch_data:
                    if isinstance(chunk, (bytes, bytearray)) and len(chunk) > 100:
                        raw_bytes = bytes(chunk)
                        break
                if raw_bytes:
                    try:
                        results.append(_parse_email_message(raw_bytes))
                    except Exception as exc:
                        logger.exception(f"Failed to parse email {msg_id}: {exc}")
            return results
        finally:
            try:
                await client.logout()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Microsoft Graph API implementation
# ---------------------------------------------------------------------------
class GraphEmailService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._token: str | None = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        try:
            from msal import ConfidentialClientApplication

            authority = (
                f"https://login.microsoftonline.com/{self.settings.email_graph_tenant_id}"
            )
            app = ConfidentialClientApplication(
                client_id=self.settings.email_graph_client_id,
                client_credential=self.settings.email_graph_client_secret,
                authority=authority,
            )
            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            token = result.get("access_token")
            if not token:
                raise RuntimeError(f"Graph token error: {result}")
            self._token = token
            return token
        except Exception as exc:
            logger.exception(f"Failed to acquire Graph API token: {exc}")
            raise

    async def fetch_unseen(self) -> list[IncomingEmail]:
        token = await self._get_token()
        user_email = self.settings.email_graph_user_email
        url = (
            f"https://graph.microsoft.com/v1.0/users/{user_email}"
            "/mailFolders/Inbox/messages?$filter=isRead eq false&$top=25"
        )
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        results: list[IncomingEmail] = []
        for item in payload.get("value", []):
            from_obj = item.get("from", {}).get("emailAddress", {})
            results.append(
                IncomingEmail(
                    message_id=item.get("internetMessageId", item.get("id", "")),
                    from_address=from_obj.get("address", ""),
                    from_name=from_obj.get("name", ""),
                    to_address=user_email or "",
                    subject=item.get("subject", ""),
                    body_plain=(item.get("body") or {}).get("content", ""),
                    body_html=None,
                    attachments=[],  # fetch separately if needed
                )
            )
        return results


def get_email_service() -> ImapEmailService | GraphEmailService:
    settings = get_settings()
    if settings.email_protocol == "graph_api":
        return GraphEmailService()
    return ImapEmailService()


# ---------------------------------------------------------------------------
# SMTP send for follow-up mails / notifications
# ---------------------------------------------------------------------------
async def send_email(
    *,
    to_address: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> bool:
    settings = get_settings()
    if not settings.email_smtp_host:
        logger.warning("SMTP not configured, cannot send email")
        return False

    msg = StdEmailMessage()
    from_name = settings.email_from_name or "RecruiterAI"
    from_addr = settings.email_from_address or settings.email_smtp_user or ""
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_address
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.email_smtp_host,
            port=settings.email_smtp_port,
            username=settings.email_smtp_user,
            password=settings.email_smtp_password,
            start_tls=settings.email_smtp_use_tls,
        )
        logger.info(f"Email sent to {to_address}: {subject}")
        return True
    except Exception as exc:
        logger.exception(f"SMTP send failed: {exc}")
        return False
