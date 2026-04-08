"""Tests for the multilingual follow-up mail fallbacks.

When Claude is unavailable, the service must still produce a sensible email
in the candidate's language. Each supported language gets a greeting line
check so regressions show up immediately.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.followup_mail import (
    _FIELD_LABELS,
    _fallback_email,
    _humanize_field,
)


def _cand(first_name: str | None):
    return SimpleNamespace(first_name=first_name)


def test_humanize_field_supports_all_languages():
    for lang in ("de", "en", "fr", "it"):
        label = _humanize_field("first_name", lang)
        assert isinstance(label, str) and label
    # Unknown field falls through to the raw name
    assert _humanize_field("unknown_field", "de") == "unknown_field"


def test_field_labels_cover_same_keys_across_languages():
    base = set(_FIELD_LABELS["en"].keys())
    for lang in ("de", "fr", "it"):
        assert set(_FIELD_LABELS[lang].keys()) == base


def test_fallback_email_de_with_name():
    mail = _fallback_email(_cand("Anna"), "de", "Telefonnummer", "KI", "Firma")
    assert "Guten Tag Anna" in mail["body"]
    assert "Telefonnummer" in mail["body"]
    assert "Beste Grüsse" in mail["body"]


def test_fallback_email_fr():
    mail = _fallback_email(_cand("Marie"), "fr", "numéro de téléphone", "KI", "Firma")
    assert "Bonjour Marie" in mail["body"]
    assert "Cordialement" in mail["body"]


def test_fallback_email_it():
    mail = _fallback_email(_cand("Luca"), "it", "numero di telefono", "KI", "Firma")
    assert "Buongiorno Luca" in mail["body"]
    assert "Cordiali saluti" in mail["body"]


def test_fallback_email_en_without_name():
    mail = _fallback_email(_cand(None), "en", "phone number", "KI", "Firma")
    assert mail["body"].startswith("Hi,")
    assert "Best regards" in mail["body"]
