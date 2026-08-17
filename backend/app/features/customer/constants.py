"""Module 6B — Customer Onboarding & Application Flow constants.

`FieldType` is a small fixed rendering-hint vocabulary the dynamic form *engine* code
understands (analogous to Dashboard's `WidgetType`) — it's closed because the renderer
has to have a switch/case for each one. The *fields themselves* (which ones exist for
which product) are fully data-driven via `ApplicationFormDefinition` (seeded, not
hardcoded) — see docs/decisions/DECISIONS.md.
"""


class FieldType:
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    SELECT = "select"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"

    ALL = (TEXT, NUMBER, DATE, SELECT, TEXTAREA, CHECKBOX)


# Phase 3.1 — a fixed vocabulary of common Indian financial-KYC formats, each mapped to
# one built-in regex in `field_validation.py` (same "engine is code, catalog is data"
# split as FieldType itself — a field only ever *names* one of these, the pattern lives
# in code once). `None`/absent means "no format-specific check beyond min/max/pattern."
class FieldFormat:
    EMAIL = "email"
    MOBILE = "mobile"
    PAN = "pan"
    AADHAAR = "aadhaar"
    IFSC = "ifsc"
    GST = "gst"
    PINCODE = "pincode"

    ALL = (EMAIL, MOBILE, PAN, AADHAAR, IFSC, GST, PINCODE)


# Phase 3.1 — conditional field visibility (`FormFieldDefinition.visible_when`). Kept to
# the 3 comparisons an equality-style condition needs; anything more (ranges, AND/OR
# trees) is deliberately out of scope until a real product needs it.
class ConditionOperator:
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"

    ALL = (EQUALS, NOT_EQUALS, IN)


# Phase 3.1 — where a SELECT field's `options` come from. STATIC is today's behavior
# (options is the actual, authored list). API is the reserved, forward-compatible shape
# for a future options_endpoint (states/cities/branches) — no such endpoint exists yet,
# this only ensures the schema/renderer never need reshaping when one is added.
class OptionsSource:
    STATIC = "static"
    API = "api"

    ALL = (STATIC, API)


# Product Schema Engine (Phase 2) — lifecycle for an `ApplicationFormDefinition`. Only
# ACTIVE schemas are served by the shared by-product lookup every portal reads
# (`find_by_product`); DRAFT lets an Owner build/edit a schema before it goes live,
# ARCHIVED retires one without deleting it (in-flight Leads/Applications already
# reference their own `form_definition_id` directly, so archiving never affects them).
class SchemaStatus:
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"

    ALL = (ACTIVE, DRAFT, ARCHIVED)


class ApplicationStatus:
    DRAFT = "draft"
    SUBMITTED = "submitted"

    ALL = (DRAFT, SUBMITTED)


# Customer Portal redesign — staff review of an uploaded ApplicationDocument. Deliberately
# 3 states only: "under review" isn't stored (a document simply exists or doesn't, and
# whether staff have acted on it is exactly `verification_status != PENDING`), and "needs
# re-upload" is just REJECTED + rejection_reason shown to the customer, not a 4th/5th state
# a re-upload would need to transition through — re-uploading is already just uploading again.
class DocumentVerificationStatus:
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

    ALL = (PENDING, VERIFIED, REJECTED)


class SecureLinkStatus:
    ACTIVE = "active"
    USED = "used"
    REVOKED = "revoked"  # surfaced to staff as "Disabled" — same underlying status

    ALL = (ACTIVE, USED, REVOKED)


# What the public resolve endpoint reports back — distinct from SecureLinkStatus (a
# stored DB value): this is a computed, request-time verdict (e.g. "expired" is never
# stored, it's derived from expires_at vs now) that the frontend routes on directly to
# pick which dedicated page to show, without needing to interpret an HTTP error code.
class LinkResolution:
    VALID = "valid"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    DISABLED = "disabled"
    ALREADY_USED = "already_used"
    ALREADY_SUBMITTED = "already_submitted"


class AuditEvent:
    CUSTOMER_REGISTERED = "customer_registered"
    # TEMPORARY — see CustomerService.bypass_verify_registration_mobile / Settings.registration_otp_bypass.
    REGISTRATION_OTP_BYPASSED = "registration_otp_bypassed"
    LEAD_CONVERTED = "lead_converted"
    SECURE_LINK_GENERATED = "secure_link_generated"
    SECURE_LINK_CLAIMED = "secure_link_claimed"
    SECURE_LINK_REVOKED = "secure_link_revoked"
    APPLICATION_STARTED = "application_started"
    APPLICATION_UPDATED = "application_updated"
    APPLICATION_SUBMITTED = "application_submitted"
    APPLICATION_ASSIGNED = "application_assigned"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_VERIFIED = "document_verified"
    DOCUMENT_REJECTED = "document_rejected"

    # Product Schema Engine governance — one entry per mutation, read back by
    # `GET /product-schemas/audit` (see CustomerService). `metadata.changes` on
    # SCHEMA_FIELD_UPDATED carries the actual old-value/new-value diff.
    SCHEMA_FIELD_UPDATED = "schema_field_updated"
    SCHEMA_DRAFT_CREATED = "schema_draft_created"
    SCHEMA_PUBLISHED = "schema_published"
    SCHEMA_FROZEN = "schema_frozen"


# LeadActivity.event_type values this module writes (free-form field on Module 6A's own
# frozen LeadActivity model, matching the exact precedent Module 9B's Lead Capture
# established — see docs/decisions/DECISIONS.md — no change needed to Module 6A itself).
class LeadTimelineEvent:
    SECURE_LINK_GENERATED = "secure_link_generated"
    SECURE_LINK_REGENERATED = "secure_link_regenerated"
    SECURE_LINK_DISABLED = "secure_link_disabled"
    SECURE_LINK_COPIED = "secure_link_copied"
    SECURE_LINK_SHARED = "secure_link_shared"
    CUSTOMER_OPENED_LINK = "customer_opened_link"
    CUSTOMER_STARTED_APPLICATION = "customer_started_application"
    CUSTOMER_SAVED_DRAFT = "customer_saved_draft"
    CUSTOMER_SUBMITTED_APPLICATION = "customer_submitted_application"
    LEAD_CONVERTED = "lead_converted"
