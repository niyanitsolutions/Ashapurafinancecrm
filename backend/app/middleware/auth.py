"""JWT verification dependency. This only decodes and validates the access token; it
does not know about the `auth` feature's user-lookup or permission model (added when
Authentication is built) — kept minimal so it is safe to wire into `main.py` now.
"""

from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import UnauthorizedError
from app.features.auth.session_lifecycle import validate_family
from app.security.jwt import TokenError, TokenType, decode_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_subject(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncIOMotorDatabase[Any] = Depends(get_database),
) -> str:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")
    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired token.") from exc
    if not payload.get("sid"):
        raise UnauthorizedError("Please login again to establish a secure session.")
    await validate_family(db, str(payload["sub"]), str(payload["sid"]),
                          activity=request.url.path.endswith("/auth/activity"))
    return str(payload["sub"])
