from typing import Any

from app.features.customer.models import Application, Customer
from app.features.loan_management.models import LoanCaseAdditionalDocument, LoanCaseBankOffer
from app.features.loan_management.schemas import (
    AdditionalDocumentResponse,
    BankOfferResponse,
    CustomerBankOfferResponse,
    LoanCaseApplicationSummary,
    LoanCaseCustomerSummary,
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


def to_list_item(
    case: ApplicationWorkflow, customer_name: str | None, product_name: str, assigned_to_name: str | None,
    allowed_next_statuses: list[str] | None = None,
) -> LoanCaseListItem:
    # Selected bank/approved amount are written onto `loan_details` by
    # `LoanCaseService._select_bank_offer_core` at selection time (decision #129) — read
    # straight off the case here rather than a separate per-row bank-offers query, so
    # the list endpoint stays a single query.
    details = case.loan_details
    return LoanCaseListItem(
        id=case.require_id(), case_code=case.case_code, application_id=case.application_id, customer_id=case.customer_id,
        customer_name=customer_name, product_id=case.product_id, product_name=product_name,
        assigned_to=case.assigned_to, assigned_to_name=assigned_to_name, current_status=case.current_status,
        rejection_reason=case.rejection_reason, allowed_next_statuses=allowed_next_statuses or [],
        selected_bank_name=details.bank_nbfc_name if details else None,
        approved_amount=details.offered_amount if details else None,
        disbursed_amount=details.disbursed_amount if details else None,
        disbursed_at=details.disbursed_at if details else None,
        created_at=case.created_at,
    )


def bank_offer_to_response(offer: LoanCaseBankOffer) -> BankOfferResponse:
    return BankOfferResponse(
        id=offer.require_id(), loan_case_id=offer.loan_case_id, bank_name=offer.bank_name,
        branch=offer.branch, loan_type=offer.loan_type, requested_amount=offer.requested_amount,
        bank_application_id=offer.bank_application_id, reference_number=offer.reference_number,
        assigned_officer=offer.assigned_officer, decision=offer.decision, approved_amount=offer.approved_amount,
        interest_rate=offer.interest_rate, tenure_months=offer.tenure_months, processing_fee=offer.processing_fee,
        emi_per_month=offer.emi_per_month,
        remarks=offer.remarks, is_selected=offer.is_selected, selected_at=offer.selected_at, selected_by=offer.selected_by,
        created_at=offer.created_at, updated_at=offer.updated_at,
    )


def bank_offer_to_customer_response(offer: LoanCaseBankOffer) -> CustomerBankOfferResponse:
    assert offer.approved_amount is not None
    return CustomerBankOfferResponse(
        id=offer.require_id(), bank_name=offer.bank_name, approved_amount=offer.approved_amount,
        interest_rate=offer.interest_rate, tenure_months=offer.tenure_months, processing_fee=offer.processing_fee,
        emi_per_month=offer.emi_per_month,
    )


def customer_to_summary(customer: Customer | None) -> LoanCaseCustomerSummary | None:
    if customer is None:
        return None
    address = customer.address
    return LoanCaseCustomerSummary(
        full_name=customer.full_name, mobile=customer.mobile, email=customer.email, date_of_birth=customer.date_of_birth,
        address_line1=address.line1 if address else None, address_line2=address.line2 if address else None,
        city=address.city if address else None, state=address.state if address else None,
        pincode=address.pincode if address else None,
    )


def application_to_summary(application: Application | None) -> LoanCaseApplicationSummary | None:
    if application is None:
        return None
    return LoanCaseApplicationSummary(
        application_code=application.application_code, product_category=application.product_category,
        status=application.status, submitted_at=application.submitted_at,
    )


def to_detail_response(
    case: ApplicationWorkflow, customer_name: str | None, product_name: str, assigned_to_name: str | None,
    allowed_next_statuses: list[str] | None = None, *, allowed_previous_statuses: list[str] | None = None,
    customer: Customer | None = None, application: Application | None = None,
    bank_offers: list[LoanCaseBankOffer] | None = None,
) -> LoanCaseDetailResponse:
    return LoanCaseDetailResponse(
        **to_list_item(case, customer_name, product_name, assigned_to_name, allowed_next_statuses).model_dump(),
        pending_document_type_ids=case.pending_document_type_ids,
        loan_details=_details_response(case),
        updated_at=case.updated_at,
        allowed_previous_statuses=allowed_previous_statuses or [],
        customer=customer_to_summary(customer),
        application=application_to_summary(application),
        bank_offers=[bank_offer_to_response(o) for o in (bank_offers or [])],
    )


def additional_document_to_response(
    doc: LoanCaseAdditionalDocument, download_url: str | None = None, attachment_url: str | None = None, verified_by_name: str | None = None,
) -> AdditionalDocumentResponse:
    return AdditionalDocumentResponse(
        id=doc.require_id(), loan_case_id=doc.loan_case_id, name=doc.name, document_status=doc.document_status,
        verification_status=doc.verification_status, rejection_reason=doc.rejection_reason, file_name=doc.file_name,
        download_url=download_url, attachment_url=attachment_url, uploaded_at=doc.uploaded_at,
        verified_by_name=verified_by_name, verified_at=doc.verified_at, created_at=doc.created_at,
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
