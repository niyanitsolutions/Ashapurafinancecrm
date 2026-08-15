"""Geo Fencing constants.

`GeoActivity` mirrors the spec's named checkboxes so the frontend/data model can offer
all of them, but only `LEAD_CREATION`, `DOCUMENT_COLLECTION`, and `LOGIN` have a real
enforcement hook wired up (see `enforcement.py`'s module docstring for why the other
three don't map to any real single employee-initiated action in this codebase) —
selecting them on a Geo Fence is accepted and stored, just inert, same "reserved value"
posture this codebase already uses elsewhere (e.g. `IntegrationConfig.health_status`).
"""


class GeoActivity:
    LEAD_CREATION = "lead_creation"
    CUSTOMER_VISIT = "customer_visit"
    DOCUMENT_COLLECTION = "document_collection"
    LOAN_APPLICATION = "loan_application"
    INSURANCE_APPLICATION = "insurance_application"
    LOGIN = "login"

    ALL = (LEAD_CREATION, CUSTOMER_VISIT, DOCUMENT_COLLECTION, LOAN_APPLICATION, INSURANCE_APPLICATION, LOGIN)
    ENFORCED = (LEAD_CREATION, DOCUMENT_COLLECTION, LOGIN)


class GeoFenceStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"

    ALL = (ACTIVE, INACTIVE)


MIN_RADIUS_METERS = 1
MAX_RADIUS_METERS = 50_000  # 50 km — generous upper bound to catch fat-fingered entry, not a business rule


class AuditEvent:
    FENCE_CREATED = "geo_fence_created"
    FENCE_UPDATED = "geo_fence_updated"
    FENCE_ACTIVATED = "geo_fence_activated"
    FENCE_DEACTIVATED = "geo_fence_deactivated"
    FENCE_DELETED = "geo_fence_deleted"
    CHECK_ALLOWED = "geo_fence_check_allowed"
    CHECK_DENIED = "geo_fence_check_denied"
