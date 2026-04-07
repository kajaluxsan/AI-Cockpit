"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


candidate_status = sa.Enum(
    "new",
    "parsed",
    "info_requested",
    "matched",
    "contacted",
    "interview",
    "placed",
    "rejected",
    name="candidatestatus",
)
candidate_source = sa.Enum(
    "email", "linkedin", "external_api", "manual", name="candidatesource"
)
job_status = sa.Enum("open", "paused", "filled", "closed", name="jobstatus")
job_source = sa.Enum("email", "linkedin", "external_api", "manual", name="jobsource")
match_status = sa.Enum(
    "new", "contacted", "interview", "placed", "rejected", name="matchstatus"
)
call_status = sa.Enum(
    "initiated",
    "ringing",
    "in_progress",
    "completed",
    "no_answer",
    "busy",
    "failed",
    "canceled",
    name="callstatus",
)
call_direction = sa.Enum("outbound", "inbound", name="calldirection")
email_direction = sa.Enum("inbound", "outbound", name="emaildirection")
email_kind = sa.Enum(
    "application", "followup_request", "reply", "notification", "other", name="emailkind"
)


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("headline", sa.String(length=300), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("experience_years", sa.Float(), nullable=True),
        sa.Column("education", sa.JSON(), nullable=True),
        sa.Column("work_history", sa.JSON(), nullable=True),
        sa.Column("salary_expectation", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=10), nullable=True),
        sa.Column("availability", sa.String(length=100), nullable=True),
        sa.Column("languages_spoken", sa.JSON(), nullable=True),
        sa.Column("source", candidate_source, nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=True),
        sa.Column("cv_text", sa.Text(), nullable=True),
        sa.Column("cv_attachment_path", sa.String(length=500), nullable=True),
        sa.Column("status", candidate_status, nullable=False),
        sa.Column("missing_fields", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_candidates_email", "candidates", ["email"])
    op.create_index("ix_candidates_status", "candidates", ["status"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_skills", sa.JSON(), nullable=True),
        sa.Column("nice_to_have_skills", sa.JSON(), nullable=True),
        sa.Column("min_experience_years", sa.Float(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=10), nullable=True),
        sa.Column("employment_type", sa.String(length=50), nullable=True),
        sa.Column("languages_required", sa.JSON(), nullable=True),
        sa.Column("source", job_source, nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=True),
        sa.Column("status", job_status, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "candidate_id",
            sa.Integer(),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", match_status, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_matches_candidate_id", "matches", ["candidate_id"])
    op.create_index("ix_matches_job_id", "matches", ["job_id"])
    op.create_index("ix_matches_status", "matches", ["status"])

    op.create_table(
        "call_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "candidate_id",
            sa.Integer(),
            sa.ForeignKey("candidates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("twilio_call_sid", sa.String(length=100), nullable=True),
        sa.Column("direction", call_direction, nullable=False),
        sa.Column("from_number", sa.String(length=50), nullable=True),
        sa.Column("to_number", sa.String(length=50), nullable=True),
        sa.Column("status", call_status, nullable=False),
        sa.Column("detected_language", sa.String(length=10), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("transcript_segments", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("interest_level", sa.String(length=50), nullable=True),
        sa.Column("next_steps", sa.Text(), nullable=True),
        sa.Column("recording_url", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_call_logs_candidate_id", "call_logs", ["candidate_id"])
    op.create_index("ix_call_logs_twilio_call_sid", "call_logs", ["twilio_call_sid"])
    op.create_index("ix_call_logs_status", "call_logs", ["status"])

    op.create_table(
        "email_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "candidate_id",
            sa.Integer(),
            sa.ForeignKey("candidates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("direction", email_direction, nullable=False),
        sa.Column("kind", email_kind, nullable=False),
        sa.Column("message_id", sa.String(length=500), nullable=True),
        sa.Column("from_address", sa.String(length=300), nullable=True),
        sa.Column("to_address", sa.String(length=300), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("attachments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_email_logs_candidate_id", "email_logs", ["candidate_id"])
    op.create_index("ix_email_logs_message_id", "email_logs", ["message_id"])
    op.create_index("ix_email_logs_direction", "email_logs", ["direction"])
    op.create_index("ix_email_logs_kind", "email_logs", ["kind"])


def downgrade() -> None:
    op.drop_table("email_logs")
    op.drop_table("call_logs")
    op.drop_table("matches")
    op.drop_table("jobs")
    op.drop_table("candidates")

    for enum in (
        email_kind,
        email_direction,
        call_direction,
        call_status,
        match_status,
        job_source,
        job_status,
        candidate_source,
        candidate_status,
    ):
        enum.drop(op.get_bind(), checkfirst=True)
