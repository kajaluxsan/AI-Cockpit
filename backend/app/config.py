"""Application configuration loaded from environment variables.

All configuration values come from a single .env file. Sources can be
toggled on/off via SOURCE_*_ENABLED flags. When a source is disabled, its
related fields are NOT validated as required.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------
    # APPLICATION
    # ---------------------------------------------------------------
    app_name: str = "RecruiterAI"
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = True
    app_log_level: str = "INFO"
    app_secret_key: str = "change-me"

    # ---------------------------------------------------------------
    # DATABASE
    # ---------------------------------------------------------------
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "recruiterai"
    postgres_user: str = "recruiterai"
    postgres_password: str = "change-me"

    # ---------------------------------------------------------------
    # SOURCE TOGGLES
    # ---------------------------------------------------------------
    source_email_enabled: bool = True
    source_linkedin_enabled: bool = False
    source_external_api_enabled: bool = False

    # ---------------------------------------------------------------
    # EMAIL SOURCE
    # ---------------------------------------------------------------
    email_protocol: Literal["imap", "graph_api"] = "imap"
    email_imap_host: str | None = None
    email_imap_port: int = 993
    email_imap_user: str | None = None
    email_imap_password: str | None = None
    email_imap_use_ssl: bool = True
    email_poll_interval_seconds: int = 60
    email_inbox_folder: str = "INBOX"

    # SMTP for follow-ups
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_smtp_user: str | None = None
    email_smtp_password: str | None = None
    email_smtp_use_tls: bool = True
    email_from_address: str | None = None
    email_from_name: str = "RecruiterAI"

    # Microsoft Graph API
    email_graph_tenant_id: str | None = None
    email_graph_client_id: str | None = None
    email_graph_client_secret: str | None = None
    email_graph_user_email: str | None = None

    # ---------------------------------------------------------------
    # LINKEDIN
    # ---------------------------------------------------------------
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_access_token: str | None = None
    linkedin_company_id: str | None = None
    linkedin_poll_interval_seconds: int = 300

    # ---------------------------------------------------------------
    # EXTERNAL API
    # ---------------------------------------------------------------
    external_api_base_url: str | None = None
    external_api_auth_type: Literal["bearer", "basic", "api_key", "none"] = "bearer"
    external_api_auth_token: str | None = None
    external_api_auth_user: str | None = None
    external_api_auth_password: str | None = None
    external_api_key_header: str = "X-API-Key"
    external_api_key_value: str | None = None

    external_api_candidates_get: str = "/candidates"
    external_api_candidates_post: str = "/candidates"
    external_api_candidates_put: str = "/candidates/{id}"
    external_api_jobs_get: str = "/jobs"
    external_api_jobs_post: str = "/jobs"
    external_api_matches_get: str = "/matches"
    external_api_matches_post: str = "/matches"

    # ---------------------------------------------------------------
    # TWILIO
    # ---------------------------------------------------------------
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    twilio_webhook_base_url: str | None = None
    twilio_status_callback_url: str | None = None

    # ---------------------------------------------------------------
    # ELEVENLABS
    # ---------------------------------------------------------------
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id_de: str | None = None
    elevenlabs_voice_id_en: str | None = None
    # Switzerland has four official languages; each needs its own voice.
    # Falls back to the EN voice if not configured so the agent doesn't
    # crash mid-call when someone switches to FR/IT.
    elevenlabs_voice_id_fr: str | None = None
    elevenlabs_voice_id_it: str | None = None
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_stability: float = 0.5
    elevenlabs_similarity_boost: float = 0.75

    # ---------------------------------------------------------------
    # DEEPGRAM
    # ---------------------------------------------------------------
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-2"
    deepgram_language_detect: bool = True

    # ---------------------------------------------------------------
    # ANTHROPIC
    # ---------------------------------------------------------------
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 4096

    # ---------------------------------------------------------------
    # MATCHING
    # ---------------------------------------------------------------
    match_threshold_percent: int = 80
    match_auto_call_enabled: bool = True
    match_auto_email_followup: bool = True
    # These fields are treated as the CRM "required" / NOT NULL set: if any of
    # them is missing after CV parsing, the candidate profile is not created
    # outright — instead a follow-up mail is sent asking for the missing info.
    # Once the reply arrives, the profile is created.
    crm_required_fields: str = (
        "first_name,last_name,email,phone"
    )
    match_missing_info_fields: str = (
        "skills,experience_years,salary_expectation,availability,location"
    )

    # ---------------------------------------------------------------
    # WEBHOOKS (inbound)
    # ---------------------------------------------------------------
    # Shared secret callers must include in the ``X-Webhook-Secret`` header
    # when POSTing to /api/messages/inbound. If unset (or empty), the endpoint
    # is open — fine for local dev, NOT acceptable for production.
    inbound_webhook_secret: str | None = None

    # ---------------------------------------------------------------
    # GDPR / Swiss FADP
    # ---------------------------------------------------------------
    # Days after a candidate reaches status=REJECTED before the background
    # purge worker anonymises the record. Set to 0 to disable automatic
    # anonymisation (recruiter must do it by hand via the API).
    gdpr_retention_days: int = 180

    # How often the purge worker runs. Keep it infrequent — once a day is
    # plenty for a retention window measured in months.
    gdpr_purge_interval_minutes: int = 1440

    # ---------------------------------------------------------------
    # AUTHENTICATION
    # ---------------------------------------------------------------
    # Shared JWT signing secret. MUST be overridden in production — the
    # default is a dev-only placeholder and is logged on startup if used
    # so nobody accidentally ships it.
    auth_jwt_secret: str = "change-me-jwt-secret"
    auth_jwt_algorithm: str = "HS256"
    # Session lifetime in minutes. Default 8h ≈ one recruiter workday.
    auth_session_minutes: int = 480
    # Cookie name + flags. ``secure`` is off by default so the dev
    # server over plain HTTP works; turn it on in production behind TLS.
    auth_cookie_name: str = "recruiterai_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # First-boot admin — if no users exist in the DB at startup, create
    # this one. Leave empty to skip bootstrap (you'd have to seed users
    # another way, e.g. a manual INSERT).
    auth_bootstrap_admin_username: str | None = None
    auth_bootstrap_admin_password: str | None = None
    auth_bootstrap_admin_email: str | None = None

    # ---------------------------------------------------------------
    # LINKEDIN (Proxycurl-compatible)
    # ---------------------------------------------------------------
    # Optional. If set, the /api/candidates/{id}/import-linkedin endpoint
    # will fetch the public profile via the Proxycurl Person Profile API
    # and merge the fields into the candidate record. Leave empty to only
    # store the URL on the candidate.
    linkedin_scraper_api_key: str | None = None
    linkedin_scraper_base_url: str = "https://nubela.co/proxycurl/api/v2/linkedin"

    # ---------------------------------------------------------------
    # AGENT IDENTITY
    # ---------------------------------------------------------------
    agent_name: str = "Lara"
    company_name: str = "RecruiterAI Schweiz"

    # ---------------------------------------------------------------
    # FRONTEND
    # ---------------------------------------------------------------
    frontend_port: int = 3000
    vite_api_url: str = "http://localhost:8000"

    # ---------------------------------------------------------------
    # CORS
    # ---------------------------------------------------------------
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # ===============================================================
    # Derived helpers
    # ===============================================================
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def missing_info_field_list(self) -> list[str]:
        return [f.strip() for f in self.match_missing_info_fields.split(",") if f.strip()]

    @property
    def crm_required_field_list(self) -> list[str]:
        return [f.strip() for f in self.crm_required_fields.split(",") if f.strip()]

    # ===============================================================
    # Source-aware validation
    # ===============================================================
    @model_validator(mode="after")
    def validate_source_configs(self) -> "Settings":
        # Email
        if self.source_email_enabled:
            if self.email_protocol == "imap":
                missing = [
                    name
                    for name, value in {
                        "EMAIL_IMAP_HOST": self.email_imap_host,
                        "EMAIL_IMAP_USER": self.email_imap_user,
                    }.items()
                    if not value
                ]
                if missing:
                    raise ValueError(
                        f"SOURCE_EMAIL_ENABLED=true (imap) requires: {', '.join(missing)}"
                    )
            elif self.email_protocol == "graph_api":
                missing = [
                    name
                    for name, value in {
                        "EMAIL_GRAPH_TENANT_ID": self.email_graph_tenant_id,
                        "EMAIL_GRAPH_CLIENT_ID": self.email_graph_client_id,
                        "EMAIL_GRAPH_CLIENT_SECRET": self.email_graph_client_secret,
                        "EMAIL_GRAPH_USER_EMAIL": self.email_graph_user_email,
                    }.items()
                    if not value
                ]
                if missing:
                    raise ValueError(
                        f"SOURCE_EMAIL_ENABLED=true (graph_api) requires: {', '.join(missing)}"
                    )

        # LinkedIn
        if self.source_linkedin_enabled:
            missing = [
                name
                for name, value in {
                    "LINKEDIN_CLIENT_ID": self.linkedin_client_id,
                    "LINKEDIN_CLIENT_SECRET": self.linkedin_client_secret,
                    "LINKEDIN_ACCESS_TOKEN": self.linkedin_access_token,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(
                    f"SOURCE_LINKEDIN_ENABLED=true requires: {', '.join(missing)}"
                )

        # External API
        if self.source_external_api_enabled:
            if not self.external_api_base_url:
                raise ValueError(
                    "SOURCE_EXTERNAL_API_ENABLED=true requires EXTERNAL_API_BASE_URL"
                )
            if self.external_api_auth_type == "bearer" and not self.external_api_auth_token:
                raise ValueError(
                    "EXTERNAL_API_AUTH_TYPE=bearer requires EXTERNAL_API_AUTH_TOKEN"
                )
            if self.external_api_auth_type == "basic" and not (
                self.external_api_auth_user and self.external_api_auth_password
            ):
                raise ValueError(
                    "EXTERNAL_API_AUTH_TYPE=basic requires EXTERNAL_API_AUTH_USER and "
                    "EXTERNAL_API_AUTH_PASSWORD"
                )
            if self.external_api_auth_type == "api_key" and not self.external_api_key_value:
                raise ValueError(
                    "EXTERNAL_API_AUTH_TYPE=api_key requires EXTERNAL_API_KEY_VALUE"
                )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
