"""Auth domain models. `User` is the single shared identity collection across all four
roles (see docs/decisions/DECISIONS.md #007) — role-specific profile data (name, address,
department, etc.) belongs to future User Management / Customer / Referral Partner
collections, not here.
"""

from datetime import datetime

from pydantic import Field

from app.constants.roles import ALL_ROLES
from app.shared.base_document import BaseDocument

# BaseDocument.status doubles as account lifecycle state for this collection:
#   pending_password — created via OTP signup, no password set yet
#   active            — normal, usable account
#   disabled          — administratively disabled (future, e.g. by Owner)
ACCOUNT_STATUS_PENDING_PASSWORD = "pending_password"
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_DISABLED = "disabled"


class User(BaseDocument):
    mobile: str
    role: str = Field(pattern=f"^({'|'.join(ALL_ROLES)})$")
    password_hash: str | None = None
    is_mobile_verified: bool = False
    # Set True only for Employees created with an Owner-set temporary password (see
    # employee/service.py::create_employee) — forces a password change before the first
    # dashboard access. Customer/Referral Partner never need this: they already can't
    # reach an active account without setting their own password first (OTP-gated or
    # secure-link registration). Owner never needs it either.
    must_change_password: bool = False


SESSION_STATUS_ACTIVE = "active"
SESSION_STATUS_LOGGED_OUT = "logged_out"
SESSION_STATUS_REVOKED = "revoked"  # killed server-side: reuse detection, or a future admin action
SESSION_STATUS_ROTATED = "rotated"  # superseded by a newer token in the same family; expected/normal


class Session(BaseDocument):
    """One row per issued refresh token, chained into a rotation family — the Session
    Management + Login History data source.

    `status` (via BaseDocument) holds SESSION_STATUS_* values. `token_id` is the JWT
    `jti` claim shared with the refresh token, used to look the row up without storing
    the raw or even hashed token as the lookup key. `family_id` is constant across every
    row produced by rotating the same original login — see docs/decisions/DECISIONS.md
    #013 (refresh token family / reuse detection) and docs/AUTHENTICATION.md.
    """

    user_id: str
    family_id: str
    token_id: str
    refresh_token_hash: str
    login_method: str
    device: str | None = None
    browser: str | None = None
    operating_system: str | None = None
    ip_address: str | None = None
    city: str | None = None
    country: str | None = None
    login_at: datetime  # when the family began — carried forward through every rotation
    logout_at: datetime | None = None
    last_activity_at: datetime
