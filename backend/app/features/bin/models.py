from datetime import datetime

from app.shared.base_document import BaseDocument


class BinEntry(BaseDocument):
    """One row per soft-deleted business record — the Bin page's data source, and the
    30-day purge job's work queue. Kept after a restore or purge (with the matching
    timestamp set) for auditability; the Bin list filters to
    `restored_at is None and purged_at is None`.

    `BaseDocument.is_deleted` etc. refer to the BinEntry ITSELF (always false — a Bin row
    is never soft-deleted); the deletion this row records is described by the explicit
    fields below.
    """

    resource_key: str  # DeletableResource.key — "leads", "loan_cases", "customers", ...
    target_collection: str  # the Mongo collection the deleted document lives in
    document_id: str  # _id (as str) of the deleted document

    module_label: str  # "Leads", "Loan Management", ...
    stage_label: str | None = None  # "Fresh", "Send For Disbursement", ...
    record_code: str | None = None  # "AFS-LEAD-0001"
    record_summary: str | None = None  # a human line — name / mobile / etc.

    # The generic `status` value the target document had before `soft_delete` overwrote
    # it with "deleted" — written back verbatim on restore so a model with a constrained
    # `status` field (e.g. Lead) validates on read.
    original_status: str | None = None

    deleted_by: str  # actor user id (overrides BaseDocument's optional field)
    deleted_by_name: str | None = None
    deleted_at: datetime  # overrides BaseDocument's optional field
    purge_at: datetime  # deleted_at + RETENTION_DAYS

    restored_at: datetime | None = None
    restored_by: str | None = None
    purged_at: datetime | None = None
