"""Tests for the runtime config file-backed store.

The store is the seam that lets the recruiter edit CRM required fields
without a redeploy, so the roundtrip (write → reload → read) and the input
validation matter.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def runtime_config_fresh(tmp_path, monkeypatch):
    """Reload the module with a fresh CV_STORAGE_DIR per test."""
    monkeypatch.setenv("CV_STORAGE_DIR", str(tmp_path))
    import app.services.runtime_config as rc

    rc = importlib.reload(rc)
    yield rc
    # Cleanup is automatic via tmp_path


def test_get_all_returns_settings_default_when_no_override(runtime_config_fresh):
    cfg = runtime_config_fresh.get_all()
    assert "crm_required_fields" in cfg
    assert isinstance(cfg["crm_required_fields"], list)


def test_update_persists_and_reloads(runtime_config_fresh):
    runtime_config_fresh.update(
        {"crm_required_fields": ["first_name", "email"]}
    )
    assert runtime_config_fresh.get_crm_required_fields() == [
        "first_name",
        "email",
    ]


def test_update_accepts_comma_string(runtime_config_fresh):
    runtime_config_fresh.update(
        {"crm_required_fields": "first_name, last_name,  phone"}
    )
    assert runtime_config_fresh.get_crm_required_fields() == [
        "first_name",
        "last_name",
        "phone",
    ]


def test_update_rejects_unknown_keys(runtime_config_fresh):
    with pytest.raises(ValueError):
        runtime_config_fresh.update({"some_random_key": True})


def test_update_rejects_invalid_field_type(runtime_config_fresh):
    with pytest.raises(ValueError):
        runtime_config_fresh.update({"crm_required_fields": [1, 2, 3]})
