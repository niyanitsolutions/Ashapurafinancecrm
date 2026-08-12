class OwnerType:
    """Owner Account Management: exactly one Primary Owner per company, plus any number
    of Secondary Owners the Primary Owner creates. Existing OwnerProfile documents
    written before this field existed (when at most one Owner could ever exist) are
    treated as Primary via the model field's default — see owner/models.py."""

    PRIMARY = "primary"
    SECONDARY = "secondary"

    ALL = (PRIMARY, SECONDARY)


class OwnerAccountStatus:
    """Values for OwnerProfile's inherited BaseDocument.status field — same reuse
    pattern as Auth's User.status and Employee's EmploymentStatus."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class AuditEvent:
    OWNER_REGISTERED = "owner_registered"
    SECONDARY_OWNER_CREATED = "secondary_owner_created"
    SECONDARY_OWNER_UPDATED = "secondary_owner_updated"
    SECONDARY_OWNER_DEACTIVATED = "secondary_owner_deactivated"
    SECONDARY_OWNER_ACTIVATED = "secondary_owner_activated"
