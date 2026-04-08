"""Parse CV text into structured candidate data using Claude."""

from __future__ import annotations

import io
from typing import Any

from loguru import logger

from app.config import get_settings
from app.services.claude_client import get_claude_client
from app.utils.prompts import CV_PARSE_PROMPT


def extract_text_from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        logger.warning(f"PDF extraction failed: {exc}")
        return ""


def extract_text_from_docx(data: bytes) -> str:
    try:
        import docx

        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)
    except Exception as exc:
        logger.warning(f"DOCX extraction failed: {exc}")
        return ""


def extract_text_from_attachment(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(data)
    if name.endswith(".docx") or name.endswith(".doc"):
        return extract_text_from_docx(data)
    if name.endswith(".txt"):
        try:
            return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return ""


async def parse_cv_text(cv_text: str) -> dict[str, Any]:
    """Use Claude to extract structured data from raw CV text."""
    if not cv_text.strip():
        return {}
    claude = get_claude_client()
    prompt = CV_PARSE_PROMPT.format(cv_text=cv_text[:20000])
    try:
        parsed = await claude.complete_json(prompt)
    except Exception as exc:
        logger.exception(f"CV parsing via Claude failed: {exc}")
        return {}
    return _normalize(parsed)


def _normalize(parsed: dict[str, Any]) -> dict[str, Any]:
    """Make sure expected keys exist and have correct types."""
    defaults: dict[str, Any] = {
        "first_name": None,
        "last_name": None,
        "full_name": None,
        "email": None,
        "phone": None,
        "address": None,
        "location": None,
        "language": None,
        "headline": None,
        "summary": None,
        "skills": [],
        "experience_years": None,
        "education": [],
        "work_history": [],
        "salary_expectation": None,
        "salary_currency": None,
        "availability": None,
        "languages_spoken": [],
    }
    for key, default in defaults.items():
        if key not in parsed or parsed[key] is None:
            parsed[key] = default

    # Derive first/last from full_name if missing, and vice versa
    if not parsed["full_name"] and (parsed["first_name"] or parsed["last_name"]):
        parsed["full_name"] = (
            f"{parsed['first_name'] or ''} {parsed['last_name'] or ''}".strip() or None
        )
    if parsed["full_name"] and not parsed["first_name"] and not parsed["last_name"]:
        parts = parsed["full_name"].strip().split()
        if len(parts) >= 2:
            parsed["first_name"] = parts[0]
            parsed["last_name"] = " ".join(parts[1:])
        elif parts:
            parsed["first_name"] = parts[0]

    return parsed


def detect_missing_fields(candidate_data: dict[str, Any]) -> list[str]:
    """Return list of missing fields based on configured required set."""
    settings = get_settings()
    required = settings.missing_info_field_list
    missing = []
    for field in required:
        value = candidate_data.get(field)
        if value is None:
            missing.append(field)
        elif isinstance(value, list) and len(value) == 0:
            missing.append(field)
        elif isinstance(value, str) and not value.strip():
            missing.append(field)
    return missing
