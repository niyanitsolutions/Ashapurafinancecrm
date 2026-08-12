"""Direct bcrypt usage, not passlib — passlib's bcrypt backend detection breaks against
bcrypt>=4.1 (passlib is unmaintained; this is a known ecosystem incompatibility, not a
choice to avoid revisiting).
"""

import re
from typing import Annotated

import bcrypt
from pydantic import AfterValidator, Field

_MAX_PASSWORD_BYTES = 72  # bcrypt's hard limit; reject rather than silently truncate

_PASSWORD_COMPLEXITY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[A-Z]"), "an uppercase letter"),
    (re.compile(r"[a-z]"), "a lowercase letter"),
    (re.compile(r"\d"), "a number"),
    (re.compile(r"[^\w\s]"), "a special character"),
]


def validate_password_strength(password: str) -> str:
    """Pydantic AfterValidator backing `PasswordStr` below — one place for the
    complexity rule instead of a copy in every schema that accepts a new password."""
    missing = [description for pattern, description in _PASSWORD_COMPLEXITY_RULES if not pattern.search(password)]
    if missing:
        raise ValueError(f"Password must contain {', '.join(missing)}.")
    return password


# Shared by every schema that accepts a new/changed password (see ResetPasswordRequest,
# ChangePasswordRequest, employee CreateEmployeeRequest) — same min/max length bcrypt
# already enforces, plus the complexity rule above.
PasswordStr = Annotated[str, Field(min_length=8, max_length=_MAX_PASSWORD_BYTES), AfterValidator(validate_password_strength)]


def hash_password(plain_password: str) -> str:
    encoded = plain_password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {_MAX_PASSWORD_BYTES} bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
