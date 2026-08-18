"""Module 6B — Customer Onboarding & Application Flow domain models.

Two supported entry flows (see docs/decisions/DECISIONS.md #046-#052):
  Flow 1 (existing Lead): Employee generates a SecureLink for a Lead (Module 6A, read-only
    reference) -> Customer registers/logs in -> Application opens directly, with no
    Customer profile yet -> Customer profile is created (the "conversion") only once the
    Application is submitted.
  Flow 2 (direct portal): Customer registers -> profile is completed immediately -> then
    picks a product and fills the (dynamic, product-specific-only) Application form.

Product Schema Engine governance (supersedes the earlier "not Owner-CRUD-able" decision):
each product has a `FormTemplateMaster` (the client's official spec, written only by
`scripts/apply_product_schema.py`, never editable via any API) and an
`ApplicationFormDefinition` (the Owner Configuration actually served to every portal). A
field/document tagged `source="master"` traces back to the template via `master_key` and
may be relabelled/hidden/reordered/re-validated but never deleted or re-keyed/re-typed by
the Owner; `source="custom"` fields are Owner-authored and fully free. See
`CustomerService.update_form_definition`'s diff-by-key merge for the enforcement, and
`SchemaStatus`/`ApplicationFormDefinition.is_locked` for the freeze/version lifecycle.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.features.customer.constants import (
    ApplicationStatus,
    ConditionOperator,
    FieldFormat,
    FieldType,
    OptionsSource,
    SchemaStatus,
    SecureLinkStatus,
)
from app.shared.base_document import BaseDocument


class Address(BaseModel):
    line1: str
    line2: str | None = None
    city: str
    state: str
    pincode: str
    country: str = "India"


class Customer(BaseDocument):
    customer_code: str  # AFS-CUS-000001
    user_id: str  # ref: users (Auth), unique — login identity stays there, decision 007's pattern

    full_name: str
    mobile: str  # denormalized from users.mobile at creation, same pattern as Employee (decision-noted risk)
    email: str | None = None
    date_of_birth: datetime | None = None  # BSON has no date-only type — see docs/database/DATABASE.md
    gender: str | None = None

    pan_number_encrypted: str | None = None
    aadhaar_number_encrypted: str | None = None

    address: Address | None = None

    # Set only when this Customer was created by converting a Lead (Flow 1) at
    # submission time — null for a Flow 2 direct-portal customer. Module 6A's `Lead` is
    # not modified to add a reverse pointer; this is the one place that relationship is
    # recorded (decision 048).
    converted_from_lead_id: str | None = None

    # BaseDocument.status: "active" (default) — a simple profile-status flag per the
    # brief; no richer lifecycle than that is asked for in 6B.


class ApplicationDocument(BaseDocument):
    application_id: str
    document_type_id: str  # ref: system_settings.document_types (Module 4, read-only)
    # `None` only for a `document_status=NOT_AVAILABLE` placeholder row (see below) — every
    # row that actually holds a file always has both.
    file_name: str | None = None
    s3_key: str | None = None
    content_type: str | None = None

    # Customer Portal redesign — staff review. Defaults PENDING so every document uploaded
    # before this existed reads exactly as it always has (uploaded, not yet reviewed).
    verification_status: str = "pending"
    verified_by: str | None = None  # ref: employees — who verified/rejected it
    verified_at: datetime | None = None
    rejection_reason: str | None = None  # set only when verification_status == "rejected"

    # Document management redesign — re-upload/versioning + the optional-document
    # "I don't have this" flow. Defaults reproduce prior behavior exactly for every row
    # written before this existed (a real uploaded file, and the only/current one), so no
    # migration is needed.
    document_status: str = "uploaded"  # DocumentAvailabilityStatus: "uploaded" | "not_available"
    file_size_bytes: int | None = None  # from an S3 HEAD at confirm time — never client-trusted
    # A `RequiredDocumentDefinition.multiple_upload=False` document type has at most one
    # `is_current=True` row at a time; re-uploading (or marking not-available) atomically
    # supersedes the previous current row (see CustomerService.confirm_document) rather
    # than leaving two "current" documents. `multiple_upload=True` types never supersede —
    # every confirmed upload stays current. `doc_version`/`replaces_document_id` exist for
    # the version-history endpoint only; ordering for display uses `created_at`, since
    # concurrent re-uploads make version numbers only advisory, not authoritative.
    is_current: bool = True
    doc_version: int = 1
    replaces_document_id: str | None = None  # ref: application_documents — the row this superseded, if any


class FieldCondition(BaseModel):
    """Phase 3.1 — `FormFieldDefinition.visible_when`: this field only renders (and is
    only required/validated) when another field in the *same* schema currently holds a
    matching value. Evaluated by `field_validation.is_field_visible` (backend) and the
    mirrored logic in `ProductSchemaForm` (frontend) — one rule, read by both."""

    field_key: str  # the controlling field's `key`, e.g. "business_type"
    operator: str = Field(default=ConditionOperator.EQUALS, pattern=f"^({'|'.join(ConditionOperator.ALL)})$")
    value: Any  # scalar for equals/not_equals, list for "in"


class FieldValidation(BaseModel):
    """Phase 3.1 — declarative validation metadata for one field. `format` selects a
    built-in regex (see `FieldFormat`/`field_validation.py`); `pattern` is an explicit,
    schema-authored regex for anything a fixed format doesn't cover. Both may be set;
    `format` is checked first."""

    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    format: str | None = Field(default=None, pattern=f"^({'|'.join(FieldFormat.ALL)})$")
    # Governance round — number/date ranges plus input-shaping hints. `mask` and
    # `auto_uppercase` are also mirrored client-side (`fieldValidation.ts`,
    # `DynamicFormField.tsx`) for live UX; `trim`/`auto_uppercase` are additionally
    # applied server-side in `field_validation.validate_field_value` before every other
    # check runs, so a value normalized on the way in is what actually gets validated.
    min_value: float | None = None
    max_value: float | None = None
    min_date: str | None = None  # ISO date string, e.g. "1900-01-01"
    max_date: str | None = None
    mask: str | None = None  # frontend input-formatting hint only, no server-side meaning
    auto_uppercase: bool = False
    trim: bool = False


class FormFieldDefinition(BaseModel):
    key: str
    label: str
    field_type: str = Field(pattern=f"^({'|'.join(FieldType.ALL)})$")
    required: bool = True
    options: list[str] | None = None  # for "select" fields only, when options_source="static"
    # Grouping label for rendering (e.g. "Basic Information") — optional so pre-existing
    # rows with no section still render as one flat group (Product Schema Engine
    # generalization, see docs/decisions/DECISIONS.md #051 amendment).
    section: str | None = None
    # Phase 3.1 additions — all optional/defaulted, so every schema seeded before this
    # round renders and validates exactly as before (no condition = always visible, no
    # validation block = required-only, static options unchanged).
    visible_when: FieldCondition | None = None
    validation: FieldValidation | None = None
    options_source: str = Field(default=OptionsSource.STATIC, pattern=f"^({'|'.join(OptionsSource.ALL)})$")
    options_endpoint: str | None = None  # reserved — only meaningful when options_source="api"
    # Governance round — see module docstring. `source`/`master_key` are how
    # `update_form_definition`'s diff-by-key merge tells a client-defined field (never
    # deletable/re-keyable/re-typeable by the Owner) from an Owner-added one (fully
    # free). Defaulting `source` to "custom" means every field seeded before this round
    # stays freely editable until a product is explicitly re-applied through the
    # governed `apply_product_schema.py` flow — nothing is retroactively locked.
    source: str = "custom"  # "master" | "custom"
    master_key: str | None = None  # the FormTemplateMaster field this was cloned from
    placeholder: str | None = None  # real, Owner-editable — falls back to a label-derived one client-side
    hidden: bool = False  # the only way to "remove" a master field from the live form


class RequiredDocumentDefinition(BaseModel):
    document_type_id: str  # ref: system_settings.document_types
    section: str | None = None  # e.g. "Identity & Address Proof", "Income Proof"
    note: str | None = None
    # Governance round — per-document metadata + the same master/custom split as fields.
    name_override: str | None = None  # Owner-editable display name; document_type's own name is the fallback
    required: bool = True
    allowed_types: list[str] | None = None  # e.g. ["pdf", "jpg", "png"] — None means "no restriction"
    max_size_mb: int | None = None
    multiple_upload: bool = False
    preview_enabled: bool = True
    source: str = "custom"  # "master" | "custom"
    hidden: bool = False


class RepeatableGroupDefinition(BaseModel):
    """Phase 3.1 — a repeatable block of fields (Co-Applicants, Partners, Nominees,
    Directors, References, ...). Submitted values live at
    `form_data[group.key] = [{field_key: value, ...}, ...]`, one dict per added block.
    Engine capability only this round — no seeded product uses one yet (see Phase 3.1
    report); Owner-authored via the same Product Schema CRUD as everything else."""

    key: str
    label: str
    add_button_label: str | None = None
    min_count: int = 0
    max_count: int | None = None
    fields: list[FormFieldDefinition] = Field(default_factory=list)


class ApplicationFormDefinition(BaseDocument):
    product_category: str  # "loan" | "insurance" — reuses Module 6A's ProductCategory values
    product_id: str  # ref: system_settings.loan_products or .insurance_products
    fields: list[FormFieldDefinition] = Field(default_factory=list)
    required_documents: list[RequiredDocumentDefinition] = Field(default_factory=list)
    repeatable_groups: list[RepeatableGroupDefinition] = Field(default_factory=list)
    # Overrides BaseDocument.status's generic "active" default with the Product Schema
    # Engine's own 3-state lifecycle. `version`/`created_by`/`created_at`/`updated_at`
    # are BaseDocument's existing fields, reused as-is — no separate "schema version"
    # concept needed, `version` already auto-increments on every update.
    status: str = Field(default=SchemaStatus.DRAFT, pattern=f"^({'|'.join(SchemaStatus.ALL)})$")
    # Governance round — freeze/version lifecycle, orthogonal to `status`. A locked
    # definition rejects further field/document edits (`update_form_definition`); the
    # only way to change one is `POST .../new-version`, which clones it into a new
    # DRAFT with `source_schema_version` pointing back here. `find_by_product` (the
    # shared read every portal uses) is unaffected — it already filters on
    # `status == active`.
    is_locked: bool = False
    frozen_at: datetime | None = None
    frozen_by: str | None = None  # ref: users — who froze it
    # `schema_version` is the Owner-facing "Version 2"/"Version 3" your ask #6 means —
    # deliberately a *separate* counter from `BaseDocument.version` (which every
    # ordinary field/document edit already bumps by design, per the Product Schema
    # Engine's original doc comment: "no separate schema version concept needed").
    # Reusing that same counter here would mean an ordinary Hide/relabel edit before a
    # freeze silently inflates what "Version 3" means — `schema_version` only ever
    # changes via `create_new_version`, so it always matches what you'd expect.
    schema_version: int = 1
    source_schema_version: int | None = None  # the schema_version this was cloned from; null for the first

    @property
    def required_document_type_ids(self) -> list[str]:
        """Flat id list for call sites that only need membership checks (e.g. submit
        validation) — not a persisted field, derived from `required_documents`.
        Governance round — excludes `hidden` entries (never asked for) and entries the
        Owner has marked `required=False` (present in the checklist, but optional)."""
        return [d.document_type_id for d in self.required_documents if d.required and not d.hidden]


class FormTemplateMaster(BaseDocument):
    """Governance round — the client's official spec for one product, written only by
    `scripts/apply_product_schema.py`. No API endpoint ever writes this collection, so
    it can never be edited through the app — "the client's official template must never
    be edited directly." `ApplicationFormDefinition` (the Owner Configuration) is what's
    actually served; this is only the read-only source of truth it was cloned from and
    is periodically refreshed against, one document per `(product_category, product_id)`.
    """

    product_category: str
    product_id: str
    fields: list[FormFieldDefinition] = Field(default_factory=list)
    required_documents: list[RequiredDocumentDefinition] = Field(default_factory=list)


class Application(BaseDocument):
    application_code: str  # AFS-APP-000001
    user_id: str  # the authenticated Customer-role user editing this application

    # Null until the "conversion" happens (Flow 1, at submission) or set immediately at
    # creation (Flow 2, profile already exists) — see module docstring.
    customer_id: str | None = None
    lead_id: str | None = None  # set only for Flow 1 (the originating Lead)

    product_category: str
    product_id: str
    form_definition_id: str  # exactly which ApplicationFormDefinition was used to render this

    form_data: dict[str, Any] = Field(default_factory=dict)  # product-specific fields only
    # Personal/contact/address/KYC collected inline while completing a Flow-1 application
    # (no Customer profile exists yet to hold them) — consumed and cleared at submission
    # once used to create the Customer profile. Always null for Flow 2 (profile already
    # exists at creation time, decision 047).
    pending_profile: dict[str, Any] | None = None

    assigned_to: str | None = None  # ref: employees (Module 2, read-only) — Owner-assignable

    status: str = Field(default=ApplicationStatus.DRAFT, pattern=f"^({'|'.join(ApplicationStatus.ALL)})$")
    submitted_at: datetime | None = None


class SecureLink(BaseDocument):
    """Redesigned (see docs/decisions/DECISIONS.md) to use a short, opaque, crypto-random
    `secure_code` as the sole public identifier instead of a JWT — the JWT carried no
    information the DB row didn't already hold (revocation/expiry were always re-checked
    against this row regardless of what the token claimed), and a JWT in a customer-facing
    URL is both unnecessarily long and exposes a signed blob for no real benefit. The
    `app.security.tokens` JWT primitive itself is left in place (unused by this module
    now, still available for future reuse), not deleted.
    """

    lead_id: str  # ref: leads (Module 6A, read-only) — never returned by a public endpoint
    secure_code: str  # short public code, e.g. "K8H91DQXWZ" — unique, indexed
    status: str = Field(default=SecureLinkStatus.ACTIVE, pattern=f"^({'|'.join(SecureLinkStatus.ALL)})$")
    expires_at: datetime
    one_time_use: bool = True  # if True, the link stops working entirely once used
    used_by_user_id: str | None = None
    used_at: datetime | None = None
    last_opened_at: datetime | None = None  # updated every time the public resolve endpoint is hit
    notification_status: dict[str, str] | None = None  # {"whatsapp": "sent"|"failed", "sms": ..., "email": ...}
