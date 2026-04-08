"""Runtime configuration overrides that the recruiter can change at runtime.

Values are stored in a single JSON file (``runtime_config.json``) inside
``CV_STORAGE_DIR`` — same docker volume as the CV files, so it survives
container restarts without needing a DB table / migration. A tiny
file-mtime cache avoids hitting the filesystem on every CRM upsert.

Today this module only overrides ``CRM_REQUIRED_FIELDS``. The API is
generic enough to grow — add more keys as needed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from loguru import logger

from app.config import get_settings

_CONFIG_PATH = Path(os.getenv("CV_STORAGE_DIR", "/data/cv")) / "runtime_config.json"
_DEFAULT_KEYS = {"crm_required_fields"}

_cache: dict[str, Any] = {}
_cache_mtime: float | None = None
_lock = Lock()


def _load_from_disk() -> dict[str, Any]:
    global _cache, _cache_mtime
    try:
        stat = _CONFIG_PATH.stat()
    except FileNotFoundError:
        _cache = {}
        _cache_mtime = None
        return _cache
    except Exception as exc:
        logger.warning(f"runtime_config: stat failed: {exc}")
        return _cache
    if _cache_mtime == stat.st_mtime:
        return _cache
    try:
        raw = _CONFIG_PATH.read_text(encoding="utf-8")
        parsed = json.loads(raw) if raw.strip() else {}
        if not isinstance(parsed, dict):
            raise ValueError("runtime_config must be a JSON object")
    except Exception as exc:
        logger.exception(f"runtime_config: load failed: {exc}")
        return _cache
    _cache = parsed
    _cache_mtime = stat.st_mtime
    return _cache


def get_all() -> dict[str, Any]:
    """Return the full runtime config merged over defaults."""
    settings = get_settings()
    with _lock:
        override = _load_from_disk()
    return {
        "crm_required_fields": override.get(
            "crm_required_fields", settings.crm_required_field_list
        ),
    }


def get_crm_required_fields() -> list[str]:
    cfg = get_all()
    value = cfg.get("crm_required_fields")
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return get_settings().crm_required_field_list


def update(patch: dict[str, Any]) -> dict[str, Any]:
    """Persist a partial update to disk. Unknown keys are rejected."""
    unknown = set(patch.keys()) - _DEFAULT_KEYS
    if unknown:
        raise ValueError(f"Unknown runtime config keys: {sorted(unknown)}")

    with _lock:
        current = dict(_load_from_disk())
        for k, v in patch.items():
            if k == "crm_required_fields":
                if isinstance(v, str):
                    v = [x.strip() for x in v.split(",") if x.strip()]
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    raise ValueError(
                        "crm_required_fields must be a list[str] or comma string"
                    )
                current[k] = v
            else:
                current[k] = v
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_PATH.write_text(
                json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.exception(f"runtime_config: write failed: {exc}")
            raise
        # Invalidate cache so the next read picks up the new file
        global _cache, _cache_mtime
        _cache = current
        try:
            _cache_mtime = _CONFIG_PATH.stat().st_mtime
        except Exception:
            _cache_mtime = None
    return get_all()
