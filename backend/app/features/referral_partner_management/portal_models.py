"""Versioned Partner onboarding DTOs; no customer or financial shadow models."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.features.customer.models import FieldValidation


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class KycField(StrictInput):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=150)
    kind: Literal[
        "text",
        "number",
        "email",
        "mobile",
        "date",
        "dropdown",
        "radio",
        "checkbox",
        "address",
        "file",
        "image",
        "pdf",
        "signature",
    ] = "text"
    required: bool = False
    hidden: bool = False
    help_text: str = Field(default="", max_length=500)
    options: list[str] = Field(default_factory=list, max_length=100)
    condition_key: str | None = None
    condition_value: str | None = None
    validation: FieldValidation | None = None
    max_length: int = Field(default=500, ge=1, le=5000)
    max_size_mb: int = Field(default=5, ge=1, le=10)
    mime_types: list[Literal["application/pdf", "image/jpeg", "image/png"]] = Field(
        default=["application/pdf", "image/jpeg", "image/png"]
    )

    @model_validator(mode="after")
    def safe_file_kinds(self) -> "KycField":
        if self.kind in {"image", "signature"}:
            self.mime_types = [mime for mime in self.mime_types if mime.startswith("image/")]
            if not self.mime_types:
                raise ValueError("Image and signature fields require an accepted image format.")
        elif self.kind == "pdf":
            self.mime_types = ["application/pdf"]
        return self


class KycConfiguration(StrictInput):
    version: int = Field(ge=0)
    fields: list[KycField] = Field(max_length=100)
    aadhaar_format: Literal["either", "pdf", "images"] = "either"
    required_agreement_ids: list[str] = Field(default_factory=list, max_length=10)
    retention_days: int = Field(default=365, ge=30, le=3650)


class KycDraft(StrictInput):
    confirm_account_number: str | None = Field(default=None, repr=False)
    version: int = Field(ge=0)
    form_version: int = Field(ge=1)
    values: dict[str, Any]
    consent: bool = False
    accepted_agreement_ids: list[str] = Field(default_factory=list, max_length=10)


class KycDecision(StrictInput):
    fields_verified: bool = False
    version: int = Field(ge=1)
    decision: Literal["under_review", "approved", "rejected", "reupload_required"]
    reason: str = Field(default="", max_length=2000)


class PartnerSettings(StrictInput):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    business_name: str | None = Field(default=None, max_length=150)
    version: int = Field(ge=1)
    account_active: bool
    submission_mode: Literal["partner_review", "direct_to_afs"]
    applicable_product_ids: list[str] = Field(default_factory=list, max_length=100)
    restrictions: str = Field(default="", max_length=1000)


class DocumentTicket(StrictInput):
    category: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    part: Literal["file", "front", "back"] = "file"
    content_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size: int = Field(gt=0, le=10 * 1024 * 1024)


class ConfirmDocument(StrictInput):
    ticket: str = Field(min_length=30, max_length=100)
    pdf_password: str | None = Field(default=None, max_length=200, repr=False)
    consent: bool


PROTECTED_FIELDS = [
    KycField(key="date_of_birth", label="Date of Birth", kind="date", required=True),
    KycField(key="pan_number", label="PAN Number", required=True),
    KycField(key="account_holder", label="Account Holder Name", required=True),
    KycField(key="bank_name", label="Bank Name", required=True),
    KycField(key="account_number", label="Account Number", required=True),
    KycField(key="ifsc", label="IFSC Code", required=True),
    KycField(key="bank_mobile", label="Bank-linked Mobile Number", kind="mobile", required=True),
    KycField(key="current_address", label="Current Address", kind="address", required=True),
    KycField(key="permanent_address", label="Permanent Address", kind="address", required=True),
    KycField(
        key="house_type",
        label="House Ownership Type",
        kind="dropdown",
        options=["own", "rented"],
        required=True,
    ),
    KycField(
        key="aadhaar_type",
        label="Aadhaar Document Type",
        kind="dropdown",
        options=["pdf", "images"],
        required=True,
    ),
    KycField(key="bank_passbook", label="Bank Passbook", kind="file", required=True),
    KycField(key="aadhaar", label="Masked Aadhaar", kind="file", required=True),
    KycField(key="pan_document", label="PAN Document", kind="file", required=True),
    KycField(
        key="own_house_proof",
        label="Own House Address Proof (electricity bill, voter ID or approved proof)",
        kind="file",
        required=True,
        condition_key="house_type",
        condition_value="own",
    ),
    KycField(
        key="rental_agreement",
        label="Rental Agreement",
        kind="file",
        required=True,
        condition_key="house_type",
        condition_value="rented",
    ),
    KycField(
        key="selfie",
        label="Recent Selfie",
        kind="image",
        required=True,
        mime_types=["image/jpeg", "image/png"],
    ),
    KycField(
        key="signature",
        label="Signature",
        kind="signature",
        required=True,
        mime_types=["image/jpeg", "image/png"],
    ),
]


class SensitiveReview(StrictInput):
    reason: str = Field(min_length=3, max_length=500)
