"""Unit tests for the CRM helper logic.

These test the pure functions that decide:

- which CRM required fields are missing from a parsed CV
- how existing candidate records are merged with new parsed data

They run without a database — ``_merge`` just mutates a plain object that
mimics the ORM model's attribute shape.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services import runtime_config
from app.services.crm import _merge, _required_missing


class _FakeCandidate(SimpleNamespace):
    """Stand-in for the SQLAlchemy Candidate model: same attribute access,
    zero DB dependency."""


def _default_candidate(**overrides):
    base = dict(
        first_name=None,
        last_name=None,
        full_name=None,
        email=None,
        phone=None,
        address=None,
        location=None,
        language=None,
        headline=None,
        summary=None,
        skills=None,
        experience_years=None,
        education=None,
        work_history=None,
        salary_expectation=None,
        salary_currency=None,
        availability=None,
        languages_spoken=None,
        updated_at=None,
    )
    base.update(overrides)
    return _FakeCandidate(**base)


def test_required_missing_flags_empty_and_blank(monkeypatch):
    monkeypatch.setattr(
        runtime_config,
        "get_crm_required_fields",
        lambda: ["first_name", "last_name", "email", "phone"],
    )
    data = {
        "first_name": "Anna",
        "last_name": "  ",   # blank string must count as missing
        "email": None,
        "phone": "+41 79 123 45 67",
    }
    missing = _required_missing(data)
    assert set(missing) == {"last_name", "email"}


def test_required_missing_returns_empty_when_all_filled(monkeypatch):
    monkeypatch.setattr(
        runtime_config,
        "get_crm_required_fields",
        lambda: ["first_name", "last_name", "email"],
    )
    data = {"first_name": "Anna", "last_name": "Meier", "email": "a@b.ch"}
    assert _required_missing(data) == []


def test_merge_only_fills_empty_slots():
    """Human-edited values must never be overwritten by parsed CV data."""
    existing = _default_candidate(
        first_name="Anna",          # already set by the recruiter
        phone=None,                  # empty → parse fills it
        summary="Hand-written note",  # must stay
    )
    parsed = {
        "first_name": "WRONG",       # will NOT overwrite
        "phone": "+41 79 000 00 00",  # WILL fill
        "summary": "Auto summary",   # will NOT overwrite
        "skills": ["python", "rust"],
    }
    _merge(existing, parsed)
    assert existing.first_name == "Anna"
    assert existing.phone == "+41 79 000 00 00"
    assert existing.summary == "Hand-written note"
    assert existing.skills == ["python", "rust"]
    assert existing.updated_at is not None


def test_merge_ignores_none_and_empty_values():
    existing = _default_candidate(last_name="Meier")
    _merge(existing, {"last_name": None, "skills": [], "headline": ""})
    assert existing.last_name == "Meier"
    assert existing.skills is None
    assert existing.headline is None
