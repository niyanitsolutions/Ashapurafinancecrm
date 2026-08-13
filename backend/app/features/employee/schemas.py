from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.features.employee.constants import DocumentType, EmploymentStatus, EmploymentType, Gender
from app.security.password import PasswordStr


class AddressSchema(BaseModel):
    line1: str
    line2: str | None = None
    city: str
    state: str
    pincode: str
    country: str = "India"


class EmergencyContactSchema(BaseModel):
    name: str
    relationship: str
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")


class BankDetailsInput(BaseModel):
    account_holder_name: str
    bank_name: str
    branch_name: str
    ifsc_code: str
    account_number: str = Field(min_length=4, max_length=34)  # plaintext in, encrypted before storage


class BankDetailsResponse(BaseModel):
    account_holder_name: str
    bank_name: str
    branch_name: str
    ifsc_code: str
    account_number_masked: str  # last 4 digits only — never return the decrypted number in a list/detail view


class CreateEmployeeRequest(BaseModel):
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    initial_password: PasswordStr
    first_name: str
    last_name: str
    display_name: str | None = None
    gender: str | None = Field(default=None, pattern=f"^({'|'.join(Gender.ALL)})$")
    date_of_birth: date | None = None
    blood_group: str | None = None
    alternative_mobile: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    email: EmailStr
    emergency_contact: EmergencyContactSchema | None = None
    current_address: AddressSchema | None = None
    permanent_address: AddressSchema | None = None
    department_id: str
    designation_id: str
    branch_id: str
    joining_date: date
    employment_type: str = Field(pattern=f"^({'|'.join(EmploymentType.ALL)})$")
    reporting_manager_id: str | None = None
    bank_details: BankDetailsInput | None = None
    product_ids: list[str] = Field(default_factory=list)


class UpdateEmployeeRequest(BaseModel):
    """Owner-only edit — the full field set except employee_code/user_id/mobile
    (mobile changes aren't supported anywhere yet, including in Auth)."""

    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    gender: str | None = Field(default=None, pattern=f"^({'|'.join(Gender.ALL)})$")
    date_of_birth: date | None = None
    blood_group: str | None = None
    alternative_mobile: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    emergency_contact: EmergencyContactSchema | None = None
    current_address: AddressSchema | None = None
    permanent_address: AddressSchema | None = None
    department_id: str | None = None
    designation_id: str | None = None
    branch_id: str | None = None
    joining_date: date | None = None
    employment_type: str | None = Field(default=None, pattern=f"^({'|'.join(EmploymentType.ALL)})$")
    reporting_manager_id: str | None = None
    status: str | None = Field(default=None, pattern=f"^({'|'.join(EmploymentStatus.ALL)})$")
    bank_details: BankDetailsInput | None = None
    product_ids: list[str] | None = None


class SelfUpdateEmployeeRequest(BaseModel):
    """Employee self-service edit — deliberately narrow. Department/designation/branch/
    employment_type/reporting_manager/status/bank_details/email are Owner-only.
    """

    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    gender: str | None = Field(default=None, pattern=f"^({'|'.join(Gender.ALL)})$")
    date_of_birth: date | None = None
    blood_group: str | None = None
    alternative_mobile: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    emergency_contact: EmergencyContactSchema | None = None
    current_address: AddressSchema | None = None
    permanent_address: AddressSchema | None = None


class EmployeeListItem(BaseModel):
    id: str
    employee_code: str
    first_name: str
    last_name: str
    display_name: str
    email: str
    mobile: str
    department_id: str
    department_name: str
    designation_id: str
    designation_name: str
    branch_id: str
    branch_name: str
    status: str
    joining_date: date
    product_ids: list[str] = Field(default_factory=list)


class EmployeeDetailResponse(BaseModel):
    id: str
    user_id: str
    employee_code: str
    first_name: str
    last_name: str
    display_name: str
    gender: str | None
    date_of_birth: date | None
    blood_group: str | None
    photo_s3_key: str | None
    mobile: str
    alternative_mobile: str | None
    email: str
    emergency_contact: EmergencyContactSchema | None
    current_address: AddressSchema | None
    permanent_address: AddressSchema | None
    department_id: str
    department_name: str
    designation_id: str
    designation_name: str
    branch_id: str
    branch_name: str
    joining_date: date
    employment_type: str
    reporting_manager_id: str | None
    status: str
    bank_details: BankDetailsResponse | None
    product_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SessionSummary(BaseModel):
    id: str
    device: str | None
    browser: str | None
    operating_system: str | None
    ip_address: str | None
    city: str | None
    country: str | None
    login_at: datetime
    last_activity_at: datetime
    status: str


class LoginHistoryEntry(BaseModel):
    event_type: str
    ip_address: str | None
    user_agent: str | None
    metadata: dict[str, Any] | None
    created_at: datetime


class ActivitySummaryResponse(BaseModel):
    total_logins: int
    failed_login_count: int
    last_login_at: datetime | None
    active_session_count: int
    account_status: str
    employment_status: str


class PhotoUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ConfirmPhotoRequest(BaseModel):
    s3_key: str


class MasterDataCreateRequest(BaseModel):
    name: str
    description: str | None = None


class MasterDataResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str


class BranchCreateRequest(BaseModel):
    name: str
    code: str
    address: AddressSchema | None = None
    phone: str | None = None


class BranchResponse(BaseModel):
    id: str
    name: str
    code: str
    address: AddressSchema | None = None
    phone: str | None = None
    status: str


class DocumentUploadUrlRequest(BaseModel):
    document_type: str = Field(pattern=f"^({'|'.join(DocumentType.ALL)})$")
    file_name: str
    content_type: str | None = None


class DocumentUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ConfirmDocumentRequest(BaseModel):
    document_type: str = Field(pattern=f"^({'|'.join(DocumentType.ALL)})$")
    file_name: str
    s3_key: str
    content_type: str | None = None


class EmployeeDocumentResponse(BaseModel):
    id: str
    document_type: str
    file_name: str
    s3_key: str
    content_type: str | None
    created_at: datetime


class EmployeeDocumentOverviewItem(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    document_type: str
    file_name: str
    s3_key: str
    content_type: str | None
    created_at: datetime


class EmployeeActivityEntry(BaseModel):
    event_type: str
    employee_id: str | None
    employee_name: str | None
    ip_address: str | None
    user_agent: str | None
    metadata: dict[str, Any] | None
    created_at: datetime
