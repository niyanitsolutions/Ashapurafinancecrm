from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.features.auth.schemas import MobileStr
from app.security.password import PasswordStr


class RegisterOwnerRequest(BaseModel):
    company_name: str
    owner_name: str
    mobile: MobileStr
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    accept_terms: bool


class RegistrationStatusResponse(BaseModel):
    owner_exists: bool


class CreateSecondaryOwnerRequest(BaseModel):
    """Primary-Owner-only. `owner_type` is never accepted from the client — the service
    always stamps SECONDARY, closing the privilege-escalation path a crafted payload
    could otherwise attempt."""

    full_name: str
    mobile: MobileStr
    email: EmailStr
    initial_password: PasswordStr


class UpdateSecondaryOwnerRequest(BaseModel):
    """Primary-Owner-only, and only ever applied to a Secondary Owner's own record (see
    OwnerService._get_secondary_or_403) — mobile isn't editable, same as Employee (no
    mobile-change support anywhere yet, including in Auth)."""

    full_name: str | None = None
    email: EmailStr | None = None


class OwnerAccountListItem(BaseModel):
    id: str
    full_name: str
    mobile: str
    email: str
    owner_type: str
    status: str
    created_at: datetime


class OwnerAccountDetailResponse(OwnerAccountListItem):
    user_id: str
    updated_at: datetime
