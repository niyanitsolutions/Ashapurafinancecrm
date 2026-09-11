from typing import Any

from app.features.customer.mappers import document_to_response
from app.features.customer.models import ApplicationDocument
from app.features.insurance_management.models import (
    InsuranceCaseAdditionalDocument,
    InsurancePaymentTransaction,
)
from app.features.insurance_management.schemas import (
    InsuranceApplicantDetailsResponse,
    InsuranceCaseDetailResponse,
    InsuranceCaseDetailsResponse,
    InsuranceCaseDocumentResponse,
    InsuranceCaseListItem,
    OtherDocumentResponse,
    PaymentHistoryResponse,
    PaymentTransactionResponse,
    RequiredDocumentsSummaryResponse,
)
from app.features.workflow_engine.models import (
    ApplicationNote,
    ApplicationStatusHistory,
    ApplicationWorkflow,
)
from app.features.workflow_engine.schemas import CaseNoteResponse, CaseTimelineEntryResponse


def _details_response(case: ApplicationWorkflow) -> InsuranceCaseDetailsResponse:
    details = case.insurance_details
    # A retired-pipeline case document carries extra keys — pydantic ignores them.
    return InsuranceCaseDetailsResponse(**(details.model_dump() if details is not None else {}))


def to_list_item(case: ApplicationWorkflow, customer_name: str | None, product_name: str, assigned_to_name: str | None) -> InsuranceCaseListItem:
    details = case.insurance_details
    return InsuranceCaseListItem(
        id=case.require_id(), case_code=case.case_code, application_id=case.application_id, customer_id=case.customer_id,
        customer_name=customer_name, product_id=case.product_id, product_name=product_name,
        assigned_to=case.assigned_to, assigned_to_name=assigned_to_name, current_status=case.current_status,
        rejection_reason=case.rejection_reason, next_follow_up_date=case.next_follow_up_date, created_at=case.created_at,
        premium_amount=details.premium_amount if details else None,
        amount_paid=details.amount_paid if details else None,
        payment_status=details.payment_status if details else None,
    )


_APPLICANT_FIELDS = set(InsuranceApplicantDetailsResponse.model_fields)


def _applicant_response(form_data: dict[str, Any] | None) -> InsuranceApplicantDetailsResponse:
    data = {k: v for k, v in (form_data or {}).items() if k in _APPLICANT_FIELDS}
    return InsuranceApplicantDetailsResponse.model_validate(data)


def to_detail_response(
    case: ApplicationWorkflow, customer_name: str | None, product_name: str, assigned_to_name: str | None,
    documents_summary: dict[str, Any], applicant_form_data: dict[str, Any] | None = None,
    assigned_to_channel: str | None = None,
) -> InsuranceCaseDetailResponse:
    return InsuranceCaseDetailResponse(
        **to_list_item(case, customer_name, product_name, assigned_to_name).model_dump(),
        insurance_details=_details_response(case),
        required_documents=RequiredDocumentsSummaryResponse(**documents_summary),
        updated_at=case.updated_at,
        on_hold_reason=case.on_hold_reason,
        on_hold_other_reason=case.on_hold_other_reason,
        applicant=_applicant_response(applicant_form_data),
        # Raw Advisor `channel` ("qr"/"non_qr") for the assigned advisor — absent (None)
        # for a legacy employee-id assignment. The frontend renders the QR/Non QR label.
        assigned_to_channel=assigned_to_channel,
    )


def case_document_to_response(
    document: ApplicationDocument, document_type_name: str, download_url: str | None, verified_by_name: str | None = None,
    attachment_url: str | None = None, *, is_in_schema: bool = True,
) -> InsuranceCaseDocumentResponse:
    base = document_to_response(document, document_type_name, download_url, verified_by_name, attachment_url=attachment_url)
    return InsuranceCaseDocumentResponse(**base.model_dump(), is_in_schema=is_in_schema)


def other_document_to_response(
    doc: InsuranceCaseAdditionalDocument, download_url: str | None = None, attachment_url: str | None = None,
) -> OtherDocumentResponse:
    return OtherDocumentResponse(
        id=doc.require_id(), insurance_case_id=doc.insurance_case_id, name=doc.name, document_status=doc.document_status,
        verification_status=doc.verification_status, rejection_reason=doc.rejection_reason, file_name=doc.file_name,
        download_url=download_url, attachment_url=attachment_url, uploaded_at=doc.uploaded_at,
        verified_at=doc.verified_at, created_at=doc.created_at,
        is_current=doc.is_current, doc_version=doc.doc_version,
    )


def payment_transaction_to_response(
    transaction: InsurancePaymentTransaction, creator_name: str | None
) -> PaymentTransactionResponse:
    return PaymentTransactionResponse(
        id=transaction.require_id(), amount=transaction.amount, running_total=transaction.running_total,
        created_by=transaction.created_by, created_by_name=creator_name, created_at=transaction.created_at,
    )


def payment_history_to_response(
    transactions: list[InsurancePaymentTransaction], creator_names: dict[str, str], unrecorded_amount: float
) -> PaymentHistoryResponse:
    items = [payment_transaction_to_response(t, creator_names.get(t.created_by or "")) for t in transactions]
    total_paid = unrecorded_amount + sum(t.amount for t in transactions)
    return PaymentHistoryResponse(transactions=items, unrecorded_amount=unrecorded_amount, total_paid=total_paid)


def note_to_response(note: ApplicationNote) -> CaseNoteResponse:
    return CaseNoteResponse(id=note.require_id(), text=note.text, created_by=note.created_by, created_at=note.created_at)


def timeline_entry_to_response(entry_type: str, doc: Any) -> CaseTimelineEntryResponse:
    if isinstance(doc, ApplicationStatusHistory):
        return CaseTimelineEntryResponse(
            type=entry_type, from_status=doc.from_status, to_status=doc.to_status, remarks=doc.remarks,
            created_by=doc.created_by, created_at=doc.created_at,
        )
    return CaseTimelineEntryResponse(type=entry_type, text=doc.text, created_by=doc.created_by, created_at=doc.created_at)
