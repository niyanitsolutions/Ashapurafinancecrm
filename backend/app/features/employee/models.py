"""Employee domain models. `Employee` holds profile/employment data only — login identity
(mobile, password_hash, role) stays on Auth's `users` collection (decision 007); `user_id`
links the two. Department/Designation/Branch are minimal master-data collections owned
here temporarily until a future Settings (Master Data) module takes them over — see
ai/decisions/2026-07-25-roadmap-settings-before-dashboard.md.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.features.employee.constants import DocumentType, EmploymentType, Gender
from app.shared.base_document import BaseDocument


class EmergencyContact(BaseModel):
    """Plain embedded value object — no base document fields (not its own collection)."""

    name: str
    relationship: str
    mobile: str


class Address(BaseModel):
    line1: str
    line2: str | None = None
    city: str
    state: str
    pincode: str
    country: str = "India"


class BankDetails(BaseModel):
    account_holder_name: str
    bank_name: str
    branch_name: str
    ifsc_code: str
    account_number_encrypted: str  # encrypted via app.security.encryption — never store plaintext


class Employee(BaseDocument):
    user_id: str
    employee_code: str

    first_name: str
    last_name: str
    display_name: str
    gender: str | None = Field(default=None, pattern=f"^({'|'.join(Gender.ALL)})$")
    # BSON has no date-only type — stored as datetime (midnight UTC); API layer
    # (schemas.py) still speaks plain `date`, converted at the service boundary.
    date_of_birth: datetime | None = None
    blood_group: str | None = None
    photo_s3_key: str | None = None

    mobile: str  # denormalized copy of users.mobile at creation time — see models.py docstring note in service.py
    alternative_mobile: str | None = None
    email: str
    emergency_contact: EmergencyContact | None = None

    current_address: Address | None = None
    permanent_address: Address | None = None

    department_id: str
    designation_id: str
    branch_id: str
    joining_date: datetime
    employment_type: str = Field(pattern=f"^({'|'.join(EmploymentType.ALL)})$")
    reporting_manager_id: str | None = None

    # Operational metadata only — used to enrich the Lead Assignment picker (product
    # specialization badge/recommendation) and for future reporting. Never consulted by
    # PermissionEngine; holding a product here grants no permission whatsoever.
    product_ids: list[str] = Field(default_factory=list)

    bank_details: BankDetails | None = None

    # BaseDocument.status holds EmploymentStatus.* values for this collection (same
    # reuse pattern as Auth's User.status — see docs/database/DATABASE.md).


class Department(BaseDocument):
    name: str
    description: str | None = None


class Designation(BaseDocument):
    name: str
    description: str | None = None


class Branch(BaseDocument):
    name: str
    code: str
    address: Address | None = None
    phone: str | None = None


class EmployeeDocument(BaseDocument):
    employee_id: str
    document_type: str = Field(pattern=f"^({'|'.join(DocumentType.ALL)})$")
    file_name: str
    s3_key: str
    content_type: str | None = None
