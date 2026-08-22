"""Module 4 — Settings (Master Data) domain models.

Departments/Designations/Branches are NOT redefined here — they're Module 2's
(`app/features/employee/models.py`), reused read+write via their existing repository
classes (see repository.py). This module owns everything else the brief asked for:
Lead Sources, Loan Products, Insurance Products, Status Masters, API Settings, Company
Settings, Notification Templates, Document Types.

`NamedMasterData` is the shared shape for the four simplest resources (Lead Source, Loan
Product, Insurance Product, Document Type — all just name+description+status). Giving
them one base class and one generic CRUD path in service.py/router.py avoids four
near-identical copies of the same logic (see docs/decisions/DECISIONS.md for this
module's decisions).
"""

from pydantic import BaseModel, Field

from app.features.employee.models import Address
from app.features.system_settings.constants import Weekday
from app.shared.base_document import BaseDocument


class NamedMasterData(BaseDocument):
    name: str
    description: str | None = None
    # Bank Statement password support — only meaningful for DocumentType (Owner marks
    # e.g. "Bank Statement" / "Salary Account Statement" / "Passbook" as
    # `supports_password=True` once, on the master-data row itself), but kept on the
    # shared base class rather than a DocumentType-only schema so the existing single
    # generic CRUD path (this module's own docstring) still serves all four resources —
    # LeadSource/LoanProduct/InsuranceProduct simply never set it. Every product schema's
    # `RequiredDocumentDefinition` that references that same `document_type_id` inherits
    # the flag automatically, so no loan product form has to declare it separately.
    supports_password: bool = False


class LeadSource(NamedMasterData):
    pass


class LoanProduct(NamedMasterData):
    pass


class InsuranceProduct(NamedMasterData):
    pass


class DocumentType(NamedMasterData):
    """Distinct from `app.features.employee.constants.DocumentType` (Module 2, frozen,
    a fixed enum for employee-document uploads specifically). This is the general,
    DB-driven document-type master for the rest of the system (leads/customers/KYC)."""


class StatusMaster(BaseDocument):
    category: str  # free text, e.g. "loan_status" / "insurance_status" / "customer_status"
    name: str
    sequence: int = 0
    description: str | None = None


class NotificationTemplate(BaseDocument):
    channel: str  # free text, e.g. "sms" / "email" / "whatsapp"
    key: str  # stable lookup key used by code, e.g. "otp_signup", "lead_assigned"
    subject: str | None = None  # email only
    body: str
    available_variables: list[str] = Field(default_factory=list)


class ApiSetting(BaseDocument):
    provider: str  # free text, e.g. "meta" / "whatsapp" / "sms" / "smtp" / "maps"
    label: str
    config_encrypted: str  # JSON blob of provider-specific keys, encrypted at rest as a whole
    is_enabled: bool = False


class BusinessHour(BaseModel):
    day: str = Field(pattern=f"^({'|'.join(Weekday.ALL)})$")
    is_closed: bool = False
    open_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    close_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class CompanySettings(BaseDocument):
    """Singleton — exactly one document, located via `singleton_key` (unique index)
    rather than a well-known ObjectId, so `find_one`/`update` stay ordinary repository
    calls. See CompanySettingsRepository.get_or_create."""

    singleton_key: str = "default"
    company_name: str
    logo_s3_key: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    business_hours: list[BusinessHour] = Field(default_factory=list)
    # Additive (UI/UX redesign initiative) — company profile fields the Company Settings
    # page never had a backend home for. Same optional-field-under-freeze precedent as
    # GeoException's geo_fence_id (decision 110): purely additive, no existing reader
    # affected by their absence.
    contact_email: str | None = None
    contact_phone: str | None = None
    address: Address | None = None
