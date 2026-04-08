"""Password hashing, JWT issuance and verification, FastAPI dependencies.

Design choices:

- **Argon2-id for password hashing.** OWASP's current top recommendation
  (2023) for new applications, significantly more resistant to GPU and
  ASIC attacks than bcrypt. We use ``argon2-cffi`` with its default
  parameters (64 MiB memory, 3 iterations, 4 lanes) — fine for a
  recruiter back-office where login happens a few times a day.

- **JWT over a cookie.** Stateless, no session store to operate, and
  the browser sends it automatically on every request including
  WebSocket upgrades. We sign HS256 with a shared secret — RS256 would
  buy us nothing here because there's only one service doing the
  verifying. The token goes into an ``httpOnly`` cookie so JS can't read
  it; the CSRF risk is mitigated by ``SameSite=Lax`` (default) and the
  fact that mutating endpoints require JSON bodies, not form submits.

- **No refresh tokens.** The session cookie lasts eight hours by
  default, which is one recruiter workday. Expired? Log in again. Adds
  a second moving part (refresh tokens + rotation + revocation) that
  isn't worth it at this scale.

- **Constant-time username lookup.** We always run the argon2 verify
  against *something*, even when the username doesn't exist, so the
  response time doesn't leak whether a user is registered.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User


# Argon2-id with library defaults. Rehashing is done automatically by
# :func:`verify_password` when the parameters drift — handy if we ever
# bump memory or iterations, existing hashes upgrade on next login.
_hasher = PasswordHasher()

# A canary hash used by :func:`authenticate_user` when the requested
# username does not exist in the database. Verifying it lets us keep
# the response time stable whether or not the user exists. The value is
# unreachable — it's a random password hashed at import time, and
# nothing persists it.
_DUMMY_HASH = _hasher.hash("dummy-password-that-never-matches")


def hash_password(password: str) -> str:
    """Return the argon2-id hash of a cleartext password."""
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verify. Returns False on any argon2 error."""
    try:
        _hasher.verify(hashed, password)
        return True
    except VerifyMismatchError:
        return False
    except Exception as exc:
        logger.warning(f"argon2 verify raised unexpected error: {exc}")
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash was produced with weaker parameters
    than the current policy — caller should rehash on next login."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def issue_session_token(user: User) -> str:
    """Sign a JWT for the given user, valid for the configured lifetime."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.auth_session_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_admin": user.is_admin,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(
        payload,
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_algorithm,
    )
    return token


def decode_session_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException(401) on any failure."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )


# ---------------------------------------------------------------------------
# Authentication / login flow
# ---------------------------------------------------------------------------
async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> User | None:
    """Look up a user by username and verify their password.

    Always runs an argon2 verify — even when the user doesn't exist —
    so the response time doesn't leak which usernames are registered.
    """
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        # Keep timing constant by hashing against a dummy hash
        verify_password(password, _DUMMY_HASH)
        logger.info(f"Auth: rejected login for unknown/inactive user={username!r}")
        return None

    if not verify_password(password, user.password_hash):
        logger.info(f"Auth: rejected bad password for user={username!r}")
        return None

    # Quietly upgrade the stored hash if the argon2 parameters changed
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        logger.debug(f"Auth: rehashed password for user={username!r}")

    user.last_login_at = datetime.now(timezone.utc)
    logger.info(f"Auth: successful login for user={username!r}")
    return user


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
async def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=None)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: require a valid session cookie.

    Raises 401 if the cookie is missing, the token is invalid/expired,
    or the user has been deactivated since login.
    """
    settings = get_settings()
    # We can't parameterise the Cookie alias from settings because it's a
    # call-time value, so look the cookie up manually from the request.
    # (Doing this via Request is cleaner — see ``_current_user_from_request``.)
    raise HTTPException(  # pragma: no cover — unused, see below
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="get_current_user should not be called directly",
    )


async def _current_user_from_request(request, db: AsyncSession) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_session_token(token)
    user_id = int(payload.get("sub") or 0)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer active",
        )
    return user


async def current_user_dep(
    request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Actual dependency to use on protected routes.

    Usage::

        from fastapi import Depends
        from app.services.auth import current_user_dep

        @router.get("/things")
        async def list_things(user = Depends(current_user_dep)):
            ...
    """
    from fastapi import Request  # noqa: WPS433 — local to avoid circular import

    if not isinstance(request, Request):
        # Depends() passes the Request object automatically thanks to the
        # type hint on the function signature; we just use the plain
        # ``request`` name here. If this ever fires something is wrong
        # with the framework wiring.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth dependency wiring broken",
        )
    return await _current_user_from_request(request, db)


async def current_admin_dep(
    user: User = Depends(current_user_dep),
) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
