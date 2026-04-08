"""Shared pytest config.

The tests below are deliberately DB-free — they exercise pure helper
functions (CRM required-field check, photo picker, webhook secret guard,
follow-up mail fallbacks, runtime-config roundtrips). No asyncpg / docker /
network required, so they run on every PR in a plain ``uv run pytest`` step.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make ``app.*`` importable when running ``pytest`` from the backend root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Quiet the app config so ``get_settings()`` doesn't complain about missing
# env vars during unit tests.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("CRM_REQUIRED_FIELDS", "first_name,last_name,email,phone")
os.environ.setdefault("CV_STORAGE_DIR", "/tmp/recruiterai-tests")

# Disable all source integrations so the Settings validator doesn't complain
# about missing IMAP / SMTP / webhook credentials in unit tests.
os.environ.setdefault("SOURCE_EMAIL_ENABLED", "false")
os.environ.setdefault("SOURCE_LINKEDIN_ENABLED", "false")
os.environ.setdefault("SOURCE_EXTERNAL_API_ENABLED", "false")
os.environ.setdefault("MATCH_AUTO_CALL_ENABLED", "false")
os.environ.setdefault("MATCH_AUTO_EMAIL_FOLLOWUP", "false")
