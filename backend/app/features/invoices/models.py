from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.features.invoices.schemas import BillingCustomer
from app.shared.base_document import BaseDocument


class Invoice(BaseDocument):
    """Stored, calculated invoice with the CRM's standard lifecycle/audit fields.

    Monetary values are canonical decimal strings in BSON, never binary floats.
    Draft deletion retains tombstones; only an eligible tail allocation may be reused.
    """

    invoice_number: str
    status: Literal["draft", "issued", "partially_paid", "paid", "cancelled"] = "draft"
    invoice_date: str
    due_date: str
    customer_id: str | None = None
    customer: BillingCustomer
    company: dict[str, Any]
    items: list[dict[str, str]]
    tax_type: Literal["IGST", "CGST_SGST"]
    place_of_supply: str = ""
    terms: str = ""
    subtotal: str
    gst_total: str
    igst_total: str
    cgst_total: str
    sgst_total: str
    grand_total: str
    amount_in_words: str
    hsn_summary: list[dict[str, str]]
    qr_value: str = ""
    created_by_name: str
    duplicated_from: str | None = None
    issued_at: datetime | None = None
    cancelled_by: str | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None

    replacement_for: str | None = None
    source_invoice_number: str | None = None
    correction_reason: str | None = None
    request_key: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)

    is_archived: bool = False
    archived_at: datetime | None = None
    archived_by: str | None = None
    archive_reason: str | None = None
    deletion_reason: str | None = None
    number_reused_from: str | None = None

    effective_revision: int = 1
    revisions: list[dict[str, Any]] = Field(default_factory=list)
    revision_proposal: dict[str, Any] | None = None
    reissued_at: datetime | None = None
