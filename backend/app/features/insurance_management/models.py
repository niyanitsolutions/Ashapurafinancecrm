"""Insurance-only domain models. `ApplicationWorkflow`/`InsuranceCaseDetails` stay in
`workflow_engine` since they're shared with Loan; this holds what is specific to the
Insurance "Policy Leads" pipeline.
"""

from datetime import datetime

from app.shared.base_document import BaseDocument


class InsuranceCaseAdditionalDocument(BaseDocument):
    """One ad-hoc, staff-named document requested against an Insurance Case during
    Policy Document / Policy Login — the mirror of `LoanCaseAdditionalDocument`.
    Deliberately NOT a row in the fixed `document_type_id` catalog
    (`ApplicationDocument`/`RequiredDocumentDefinition`): that catalog is shared master
    data configured on the Product Schema, while this is a free-text name a staff member
    types for one specific case (e.g. "Previous Policy Copy"). Never touches
    `ApplicationFormDefinition`. Reuses the same S3 presigned-URL storage primitive as
    every other document here — this model is only the metadata row on top of it.
    """

    insurance_case_id: str
    application_id: str
    name: str

    document_status: str = "requested"  # "requested" | "uploaded"
    verification_status: str = "pending"  # "pending" | "verified" | "rejected"
    rejection_reason: str | None = None

    s3_key: str | None = None
    file_name: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    uploaded_at: datetime | None = None

    verified_by: str | None = None
    verified_at: datetime | None = None
