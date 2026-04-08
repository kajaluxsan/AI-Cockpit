"""Reusable email template model.

Templates are stored per (name, language) so a single template can ship
in four languages simultaneously. The body is plain text with simple
``{{placeholders}}`` — no full templating language to keep the attack
surface minimal (no Jinja sandbox, no user-controlled code path).

Supported placeholders (rendered by ``app.services.email_templates``):

- ``{{first_name}}``, ``{{last_name}}``, ``{{full_name}}``
- ``{{headline}}``, ``{{skills}}``, ``{{recent_jobs}}``
- ``{{agent_name}}``, ``{{company_name}}``
- ``{{signature}}`` — expands to the template marked ``is_signature=True``
  for the matching language

``is_signature=True`` marks a template as the user's email footer
(name, title, phone, etc.). The Settings UI lets the recruiter edit a
signature template per language.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmailTemplate(Base):
    __tablename__ = "email_templates"
    __table_args__ = (
        UniqueConstraint("name", "language", name="uq_email_templates_name_lang"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="de")
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Signature templates are rendered into ``{{signature}}`` of other
    # templates. There should be at most one signature per language but
    # we don't enforce that at the DB level — the service layer just
    # picks whichever one ``updated_at`` is newest.
    is_signature: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
