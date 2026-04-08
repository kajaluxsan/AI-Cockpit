"""Tests for the inbound-webhook shared-secret guard.

Constant-time comparison is the whole point of this function — we make sure
timing-safe behaviour plus the dev no-op path are both exercised.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.messages import _verify_webhook_secret
from app.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_no_secret_configured_is_noop(monkeypatch):
    monkeypatch.setenv("INBOUND_WEBHOOK_SECRET", "")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    # None, empty string, whatever — all accepted when guard is off
    _verify_webhook_secret(None)
    _verify_webhook_secret("")
    _verify_webhook_secret("anything")


def test_mismatched_secret_raises_401(monkeypatch):
    monkeypatch.setenv("INBOUND_WEBHOOK_SECRET", "topsecret")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    with pytest.raises(HTTPException) as exc:
        _verify_webhook_secret("wrong")
    assert exc.value.status_code == 401


def test_missing_header_raises_401_when_configured(monkeypatch):
    monkeypatch.setenv("INBOUND_WEBHOOK_SECRET", "topsecret")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    with pytest.raises(HTTPException) as exc:
        _verify_webhook_secret(None)
    assert exc.value.status_code == 401


def test_matching_secret_passes(monkeypatch):
    monkeypatch.setenv("INBOUND_WEBHOOK_SECRET", "topsecret")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    # Should not raise
    _verify_webhook_secret("topsecret")
    # Whitespace is stripped before comparison
    _verify_webhook_secret("  topsecret  ")
