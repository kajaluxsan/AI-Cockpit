"""crm extension: first_name/last_name/photo_url/address/cv_filename on candidates, chat_messages table

Revision ID: 0002
Revises: 0001
Create Date: 2024-02-01 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


chat_role = sa.Enum("user", "assistant", "tool", "system", name="chatrole")


def upgrade() -> None:
    # --- candidates: new CRM columns ---
    op.add_column("candidates", sa.Column("first_name", sa.String(length=120), nullable=True))
    op.add_column("candidates", sa.Column("last_name", sa.String(length=120), nullable=True))
    op.add_column("candidates", sa.Column("address", sa.String(length=300), nullable=True))
    op.add_column("candidates", sa.Column("photo_url", sa.String(length=500), nullable=True))
    op.add_column("candidates", sa.Column("cv_filename", sa.String(length=300), nullable=True))

    # --- chat_messages ---
    chat_role.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "candidate_id",
            sa.Integer(),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", chat_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=True),
        sa.Column("tool_payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_chat_messages_candidate_id", "chat_messages", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_candidate_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    chat_role.drop(op.get_bind(), checkfirst=True)

    op.drop_column("candidates", "cv_filename")
    op.drop_column("candidates", "photo_url")
    op.drop_column("candidates", "address")
    op.drop_column("candidates", "last_name")
    op.drop_column("candidates", "first_name")
