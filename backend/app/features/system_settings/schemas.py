from datetime import datetime

from pydantic import BaseModel, Field

from app.features.employee.schemas import AddressSchema
from app.features.system_settings.constants import Weekday

# ---------------------------------------------------------------------- named master data
# Shared by Lead Sources, Loan Products, Insurance Products, Document Types, and reused
# for Department/Designation edit (Module 2's own create/list schemas stay in
# employee/schemas.py — this module only adds what Module 2 didn't have: update).


class NamedMasterDataCreateRequest(BaseModel):
    name: str
    description: str | None = None


class NamedMasterDataUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class NamedMasterDataResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class BranchUpdateRequest(BaseModel):
    name: str | None = None
    code: str | None = None
    address: AddressSchema | None = None
    phone: str | None = None


# ---------------------------------------------------------------------- status masters


class StatusMasterCreateRequest(BaseModel):
    category: str
    name: str
    sequence: int = 0
    description: str | None = None


class StatusMasterUpdateRequest(BaseModel):
    name: str | None = None
    sequence: int | None = None
    description: str | None = None


class StatusMasterResponse(BaseModel):
    id: str
    category: str
    name: str
    sequence: int
    description: str | None = None
    status: str


# ---------------------------------------------------------------------- notification templates


class NotificationTemplateCreateRequest(BaseModel):
    channel: str
    key: str
    subject: str | None = None
    body: str
    available_variables: list[str] = Field(default_factory=list)


class NotificationTemplateUpdateRequest(BaseModel):
    subject: str | None = None
    body: str | None = None
    available_variables: list[str] | None = None


class NotificationTemplateResponse(BaseModel):
    id: str
    channel: str
    key: str
    subject: str | None = None
    body: str
    available_variables: list[str]
    status: str


# ---------------------------------------------------------------------- API settings
# `config` is write-only — never echoed back in plaintext (see docs/decisions/DECISIONS.md).
# The response exposes only the configured key *names* so the Owner can tell what's set.


class ApiSettingCreateRequest(BaseModel):
    provider: str
    label: str
    config: dict[str, str] = Field(default_factory=dict)
    is_enabled: bool = False


class ApiSettingUpdateRequest(BaseModel):
    label: str | None = None
    config: dict[str, str] | None = None
    is_enabled: bool | None = None


class ApiSettingResponse(BaseModel):
    id: str
    provider: str
    label: str
    configured_keys: list[str]
    is_enabled: bool
    status: str
    updated_at: datetime


# ---------------------------------------------------------------------- company settings


class BusinessHourSchema(BaseModel):
    day: str = Field(pattern=f"^({'|'.join(Weekday.ALL)})$")
    is_closed: bool = False
    open_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    close_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class UpdateCompanySettingsRequest(BaseModel):
    company_name: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    business_hours: list[BusinessHourSchema] | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: AddressSchema | None = None


class CompanySettingsResponse(BaseModel):
    id: str
    company_name: str
    logo_s3_key: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    business_hours: list[BusinessHourSchema]
    contact_email: str | None = None
    contact_phone: str | None = None
    address: AddressSchema | None = None
    updated_at: datetime


class LogoUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ConfirmLogoRequest(BaseModel):
    s3_key: str
