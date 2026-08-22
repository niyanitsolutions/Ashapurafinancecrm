from typing import Any

from app.features.loan_management.models import LoanCaseBankOffer
from app.features.loan_management.schemas import (
    BankOfferResponse,
    CustomerBankOfferResponse,
    LoanCaseDetailResponse,
    LoanCaseDetailsResponse,
    LoanCaseListItem,
)
from app.features.workflow_engine.models import (
    ApplicationNote,
    ApplicationStatusHistory,
    ApplicationWorkflow,
)
from app.features.workflow_engine.schemas import CaseNoteResponse, CaseTimelineEntryResponse


def _details_response(case: ApplicationWorkflow) -> LoanCaseDetailsResponse:
    details = case.loan_details
    assert details is not None
    return LoanCaseDetailsResponse(**details.model_dump())


def to_list_item(case: ApplicationWorkflow, customer_name: str | None, product_name: str, assigned_to_name: str | None) -> LoanCaseListItem:
    # Selected bank/approved amount are written onto `loan_details` by
    # `LoanCaseService._select_bank_offer_core` at selection time (decision #129) — read
    # straight off the case here rather than a separate per-row bank-offers query, so
    # the list endpoint stays a single query.
    details = case.loan_details
    return LoanCaseListItem(
        id=case.require_id(), case_code=case.case_code, application_id=case.application_id, customer_id=case.customer_id,
        customer_name=customer_name, product_id=case.product_id, product_name=product_name,
        assigned_to=case.assigned_to, assigned_to_name=assigned_to_name, current_status=case.current_status,
        rejection_reason=case.rejection_reason,
        selected_bank_name=details.bank_nbfc_name if details else None,
        approved_amount=details.offered_amount if details else None,
        created_at=case.created_at,
    )


def bank_offer_to_response(offer: LoanCaseBankOffer) -> BankOfferResponse:
    return BankOfferResponse(
        id=offer.require_id(), loan_case_id=offer.loan_case_id, bank_name=offer.bank_name,
        bank_application_id=offer.bank_application_id, reference_number=offer.reference_number,
        assigned_officer=offer.assigned_officer, decision=offer.decision, approved_amount=offer.approved_amount,
        remarks=offer.remarks, is_selected=offer.is_selected, selected_at=offer.selected_at, selected_by=offer.selected_by,
        created_at=offer.created_at, updated_at=offer.updated_at,
    )


def bank_offer_to_customer_response(offer: LoanCaseBankOffer) -> CustomerBankOfferResponse:
    assert offer.approved_amount is not None
    return CustomerBankOfferResponse(id=offer.require_id(), bank_name=offer.bank_name, approved_amount=offer.approved_amount)


def to_detail_response(case: ApplicationWorkflow, customer_name: str | None, product_name: str, assigned_to_name: str | None) -> LoanCaseDetailResponse:
    return LoanCaseDetailResponse(
        **to_list_item(case, customer_name, product_name, assigned_to_name).model_dump(),
        pending_document_type_ids=case.pending_document_type_ids,
        loan_details=_details_response(case),
        updated_at=case.updated_at,
    )


def note_to_response(note: ApplicationNote) -> CaseNoteResponse:
    return CaseNoteResponse(id=note.require_id(), text=note.text, created_by=note.created_by, created_at=note.created_at)


def timeline_entry_to_response(entry_type: str, doc: Any) -> CaseTimelineEntryResponse:
    if isinstance(doc, ApplicationStatusHistory):
        return CaseTimelineEntryResponse(
            type=entry_type, from_status=doc.from_status, to_status=doc.to_status, remarks=doc.remarks,
            created_by=doc.created_by, created_at=doc.created_at,
        )
    return CaseTimelineEntryResponse(type=entry_type, text=doc.text, created_by=doc.created_by, created_at=doc.created_at)
