"""Authentication router: login, logout, who-am-I.

Exposes three endpoints that the frontend talks to:

- ``POST /api/auth/login`` — username + password → session cookie
- ``POST /api/auth/logout`` — clears the session cookie
- ``GET /api/auth/me`` — returns the current user (401 if not logged in)

All three use the JWT-in-cookie scheme documented in
:mod:`app.services.auth`. Nothing here holds server-side state; logging
out is purely a cookie clear on the client, which is fine given the
short token lifetime and the fact that we don't expose the token to JS.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth import (
    authenticate_user,
    clear_session_cookie,
    current_user_dep,
    issue_session_token,
    set_session_cookie,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    is_admin: bool
    is_active: bool

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_admin=user.is_admin,
            is_active=user.is_active,
        )


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Verify credentials and drop a session cookie on the response.

    Returns the same shape as ``GET /me`` so the frontend can populate
    its auth context in one round-trip instead of two.
    """
    user = await authenticate_user(db, payload.username, payload.password)
    if user is None:
        # Generic 401 — no hint about whether the username or password
        # was wrong so we don't help anyone enumerate valid usernames.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    # ``authenticate_user`` mutated ``last_login_at`` and may have
    # rehashed the stored password; commit both.
    await db.commit()
    token = issue_session_token(user)
    set_session_cookie(response, token)
    logger.info(f"Auth: issued session for user={user.username!r}")
    return UserOut.from_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    """Clear the session cookie. Safe to call when not logged in."""
    clear_session_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user_dep)) -> UserOut:
    """Return the currently authenticated user, or 401."""
    return UserOut.from_user(user)
