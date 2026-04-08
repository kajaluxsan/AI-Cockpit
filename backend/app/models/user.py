"""User model for recruiter authentication.

Each recruiter logs in with a username + password. The password is
stored as an argon2 hash — never in cleartext — and verified via
``app.services.auth``. ``is_admin`` gates destructive actions like
creating new users or changing global runtime settings.

The model is deliberately small: we don't do per-record ACLs. Every
authenticated recruiter sees every candidate, which matches how a
small personal-recruiting agency actually works. Multi-tenant splits
can be added later without schema pain because the audit columns
(``created_by_user_id`` on candidates, etc.) would just get attached
once that requirement shows up.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, nullable=False
    )
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Argon2-id hash of the password (includes salt + parameters inline).
    # Treat as opaque — only ``app.services.auth`` knows how to verify it.
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)

    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
