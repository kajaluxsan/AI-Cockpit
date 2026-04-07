"""Language detection helper (DE / EN)."""

from __future__ import annotations

import re

from loguru import logger

from app.services.claude_client import get_claude_client
from app.utils.prompts import LANGUAGE_DETECT_PROMPT

# Very small heuristic for the most obvious cases. Falls back to Claude.
GERMAN_HINTS = {
    "der", "die", "das", "und", "ich", "du", "wir", "ihr", "sie", "ist",
    "nicht", "auch", "mit", "für", "von", "auf", "schweiz", "grüezi",
    "bewerbung", "beruf", "stelle", "arbeit", "danke", "bitte", "ja",
    "nein", "vielen", "guten", "tag", "morgen", "hallo",
}
ENGLISH_HINTS = {
    "the", "and", "you", "we", "they", "with", "from", "for", "this",
    "that", "have", "are", "is", "thank", "thanks", "please", "yes",
    "no", "hello", "hi", "good", "morning",
}


def heuristic_detect(text: str) -> str | None:
    if not text:
        return None
    words = re.findall(r"[a-zäöüß]+", text.lower())
    if not words:
        return None
    de_score = sum(1 for w in words if w in GERMAN_HINTS)
    en_score = sum(1 for w in words if w in ENGLISH_HINTS)
    if de_score == 0 and en_score == 0:
        return None
    return "de" if de_score >= en_score else "en"


async def detect_language(text: str) -> str:
    """Return 'de' or 'en'. Heuristic first, Claude fallback."""
    guess = heuristic_detect(text)
    if guess:
        return guess
    try:
        claude = get_claude_client()
        result = await claude.complete(
            LANGUAGE_DETECT_PROMPT.format(text=text[:1000]),
            temperature=0.0,
            max_tokens=10,
        )
        result = result.strip().lower()
        if result.startswith("de"):
            return "de"
        if result.startswith("en"):
            return "en"
    except Exception as exc:
        logger.warning(f"Language detection via Claude failed: {exc}")
    return "de"  # default for Switzerland
