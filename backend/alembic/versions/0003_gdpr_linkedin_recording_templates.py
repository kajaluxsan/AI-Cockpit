"""gdpr + auth + linkedin + call recording + email templates

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-08 00:00:00.000000

Adds:
- candidates.linkedin_url
- candidates GDPR columns (consent + deletion + retention)
- call_logs recording columns (url, duration)
- email_templates table
- users table
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- candidates: linkedin + GDPR ---
    op.add_column(
        "candidates",
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "candidates",
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidates",
        sa.Column("consent_source", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "deletion_requested_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "anonymised",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "candidates",
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=True),
    )

    # --- call_logs: recording ---
    op.add_column(
        "call_logs",
        sa.Column("recording_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("recording_duration_seconds", sa.Integer(), nullable=True),
    )

    # --- email_templates ---
    op.create_table(
        "email_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="de"),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "is_signature",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", "language", name="uq_email_templates_name_lang"),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    op.drop_table("email_templates")
    op.drop_column("call_logs", "recording_duration_seconds")
    op.drop_column("call_logs", "recording_url")
    op.drop_column("candidates", "retain_until")
    op.drop_column("candidates", "anonymised")
    op.drop_column("candidates", "deletion_requested_at")
    op.drop_column("candidates", "consent_source")
    op.drop_column("candidates", "consent_given_at")
    op.drop_column("candidates", "linkedin_url")
