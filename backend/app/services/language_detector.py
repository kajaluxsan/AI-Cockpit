"""Language detection helper (DE / EN / FR / IT).

Switzerland is quadrilingual so the Swiss recruiting scenario needs all four.
The cheap heuristic catches the common cases (99% of CVs and emails have
enough stopwords); anything ambiguous falls back to Claude which returns one
of the four codes.
"""

from __future__ import annotations

import re

from loguru import logger

from app.services.claude_client import get_claude_client
from app.utils.prompts import LANGUAGE_DETECT_PROMPT

SUPPORTED = ("de", "en", "fr", "it")

# Cheap stopword heuristic — covers the obvious cases. Only the most common
# stopwords per language so we don't bloat the lookup sets.
_HINTS: dict[str, set[str]] = {
    "de": {
        "der", "die", "das", "und", "ich", "du", "wir", "ihr", "sie", "ist",
        "nicht", "auch", "mit", "für", "von", "auf", "schweiz", "grüezi",
        "bewerbung", "beruf", "stelle", "arbeit", "danke", "bitte", "ja",
        "nein", "vielen", "guten", "tag", "morgen", "hallo",
    },
    "en": {
        "the", "and", "you", "we", "they", "with", "from", "for", "this",
        "that", "have", "are", "is", "thank", "thanks", "please", "yes",
        "no", "hello", "hi", "good", "morning",
    },
    "fr": {
        "le", "la", "les", "un", "une", "des", "et", "ou", "je", "tu",
        "nous", "vous", "ils", "elles", "est", "avec", "pour", "sur",
        "bonjour", "merci", "oui", "non", "candidature", "poste", "travail",
        "entreprise", "expérience", "cordialement",
    },
    "it": {
        "il", "la", "lo", "gli", "le", "un", "una", "e", "o", "io", "tu",
        "noi", "voi", "loro", "è", "con", "per", "su", "buongiorno",
        "grazie", "sì", "no", "candidatura", "lavoro", "azienda",
        "esperienza", "cordiali", "saluti",
    },
}


def heuristic_detect(text: str) -> str | None:
    if not text:
        return None
    words = re.findall(r"[a-zàâäéèêëîïôöùûüÿçñß]+", text.lower())
    if not words:
        return None
    scores = {lang: sum(1 for w in words if w in hints) for lang, hints in _HINTS.items()}
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return None
    return best


async def detect_language(text: str) -> str:
    """Return one of ``de|en|fr|it``. Heuristic first, Claude fallback."""
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
        for code in SUPPORTED:
            if result.startswith(code):
                return code
    except Exception as exc:
        logger.warning(f"Language detection via Claude failed: {exc}")
    return "de"  # default for Switzerland
